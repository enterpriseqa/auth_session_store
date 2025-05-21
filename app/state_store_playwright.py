# main.py (FastAPI server)

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional  # Added Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, status
from pydantic import BaseModel, HttpUrl
from playwright.async_api import async_playwright, Playwright, BrowserContext, Page

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.agent.remote_ocragent import RemoteOCRLLM
from app.utils.utils import get_page_screenshot

# --- Configuration (same) ---
STATE_STORAGE_BASE_DIR = Path(os.getenv("STATE_STORAGE_DIR"))
STATE_STORAGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
STATE_STORAGE_DIR = STATE_STORAGE_BASE_DIR / "state_storage"
STATE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
USER_DATA_PROFILE_DIR = STATE_STORAGE_DIR / "user_data_profile"
USER_DATA_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

X_API_KEY = os.getenv("X_API_KEY")
OCR_AGENT_BASE_URL = os.getenv("OCR_AGENT_BASE_URL")

# --- Application State (same) ---
app_state: Dict[str, Dict[str, Any]] = {}

class StartLoginBody(BaseModel):
    username: str
    login_url: HttpUrl


class StoreStateBody(BaseModel):
    username: str
    login_url: HttpUrl


class UseStateBody(BaseModel):
    username: str
    login_url: HttpUrl   # The URL used during the initial login to identify the profile/state
    # The URL to navigate to, now optional
    target_url: Optional[HttpUrl] = None
    expected_text_after_login: Optional[str] = None
    expected_text_timeout_ms: Optional[int] = 20000
    

agent = RemoteOCRLLM(
    api_key=X_API_KEY,
    api_endpoint=f"{OCR_AGENT_BASE_URL}"
)

def sanitize_for_path(text: str) -> str:
    return re.sub(r'[^\w.-]', '_', text)


def get_login_url_identifier(login_url: HttpUrl) -> str:
    parsed_url = urlparse(str(login_url))
    return sanitize_for_path(parsed_url.netloc)


def get_session_id(username: str, login_url: HttpUrl) -> str:
    url_identifier = get_login_url_identifier(login_url)
    return f"{sanitize_for_path(username)}@{url_identifier}"


def get_user_profile_dir(username: str, login_url: HttpUrl) -> Path:
    url_identifier = get_login_url_identifier(login_url)
    return USER_DATA_PROFILE_DIR / sanitize_for_path(username) / url_identifier


def get_exported_state_filepath(username: str, login_url: HttpUrl) -> Path:
    url_identifier = get_login_url_identifier(login_url)
    user_state_dir = STATE_STORAGE_DIR / sanitize_for_path(username)
    user_state_dir.mkdir(parents=True, exist_ok=True)
    return user_state_dir / f"{url_identifier}_state.json"

def remove_state_file(state_file_path):
    if (Path.exists(state_file_path)):
        os.remove(state_file_path)


async def _launch_browser_and_navigate_task(
    username: str,
    session_id: str,
    login_url: HttpUrl,
    user_specific_profile_dir: Path
):
    try:
        pw_instance = await async_playwright().start()
    except RuntimeError as e:
        raise Exception(str(e))
    
    print(
        f"Starting browser launch for session {session_id}...")
    app_state[session_id]["status"] = "launching"
    user_specific_profile_dir.mkdir(parents=True, exist_ok=True)
    context: BrowserContext | None = None
    try:
        context = await pw_instance.chromium.launch_persistent_context(
            user_data_dir=user_specific_profile_dir,
            headless=False,
            channel="chrome",
            args=['--no-first-run', '--no-default-browser-check',
                  '--disable-blink-features=AutomationControlled'],
            ignore_default_args=['--enable-automation']
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(str(login_url), wait_until="domcontentloaded")
        app_state[session_id].update(
            {"context": context, "page": page, "status": "ready"})
        print(
            f"Browser session {session_id} ready. User should log in at {login_url}.")
        
        input(f"\n>>> ACTION REQUIRED: Browser window should be open for {username} at {login_url}.\n"
            f"    Please complete the manual login process in that browser window.\n"
            f"    Once logged in, press Enter here to continue...\n")
        
        state_file_path = get_exported_state_filepath(username, login_url)
        await context.storage_state(path=str(state_file_path))
    except Exception as e:
        print(
            f"ERROR: Failed to launch browser for session {session_id}: {e}")
        app_state[session_id]["status"] = "failed"
        app_state[session_id]["error"] = str(e)
    finally: 
        if context:
            try:
                await context.close()
            except Exception as close_e:
                print(
                    f"ERROR: Could not close context for failed session {session_id}: {close_e}")
        if pw_instance:
            await pw_instance.stop()


async def start_login_session_store_state(request: StartLoginBody):
    username = request.username
    login_url = request.login_url
    session_id = get_session_id(username, login_url)
    user_specific_profile_dir = get_user_profile_dir(username, login_url)

    if session_id in app_state and app_state[session_id].get("status") in ["launching", "ready"]:
        raise Exception(f"Session {session_id} is already active or launching {app_state[session_id]['status']}")
    app_state[session_id] = {
        "context": None, "page": None, "login_url": str(login_url), "username": username,
        "user_data_dir": user_specific_profile_dir, "status": "pending"
    }
    await _launch_browser_and_navigate_task(username, session_id, login_url, user_specific_profile_dir )
    print(
        f"API: Request to start login for session {session_id} received. Task added to background.")
    return {"message": f"Request received to start login session {session_id} for {username} at {login_url}. Browser will launch in background."}





async def use_exported_state_and_validate_session(request: UseStateBody):
    pw_instance = await async_playwright().start()
    username = request.username
    login_url_for_state = request.login_url
    # Use target_url if provided, otherwise default to login_url_for_state
    actual_target_url = request.target_url if request.target_url else login_url_for_state

    state_file_path = get_exported_state_filepath(
        username, login_url_for_state)
    session_id_for_log = get_session_id(username, login_url_for_state)

    if not state_file_path.exists():
        raise Exception(f"No exported state file found for session {session_id_for_log} at {state_file_path}")

    browser = None
    context = None
    try:
        browser = await pw_instance.chromium.launch(headless=True,
                                                    args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    storage_state=str(state_file_path)
)
        page = await context.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})
        print(
            f"API: Navigating to {actual_target_url} for session {session_id_for_log} using exported state from {state_file_path}...")
        await page.goto(str(actual_target_url), wait_until="domcontentloaded")
        await asyncio.sleep(10)
        
        screenshot_dir = STATE_STORAGE_DIR / sanitize_for_path(username)
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        url_identifier = get_login_url_identifier(login_url_for_state)
        screenshot_path = screenshot_dir / \
            f"{url_identifier}_persistent_profile_target_screenshot_pre.png"
        screenshot = await get_page_screenshot(page, path=screenshot_path)
        
        if request.expected_text_after_login:
            print(f"API: Attempting to verify login by checking for text: '{request.expected_text_after_login}'")
            try:
                agent_output = await agent.ainvoke(screenshot,request.expected_text_after_login )
                if (not request.expected_text_after_login in agent_output.extracted_text):
                    raise Exception("failed to identify the searched text")
                verification_message = f"Login successfully verified: Found text '{request.expected_text_after_login}'."
                print(f"API: {verification_message} for session {session_id_for_log}")
            except PlaywrightTimeoutError:
                remove_state_file(state_file_path)
                verification_message = f"Login verification failed: Text '{request.expected_text_after_login}' not visible within {request.expected_text_timeout_ms}ms."
                print(f"API: {verification_message} for session {session_id_for_log}")
            except Exception as e_verify:
                remove_state_file(state_file_path)
                verification_message = f"Error during login verification for text '{request.expected_text_after_login}': {str(e_verify)}"
                print(f"API: {verification_message} for session {session_id_for_log}")        
        title = await page.title()
        screenshot_path = state_file_path.parent / \
            f"{state_file_path.stem}_target_screenshot.png"
        await page.screenshot(path=screenshot_path)

        return {
            "message": f"Successfully navigated to {actual_target_url} for session {session_id_for_log} using exported state.",
            "title": title,
            "screenshot": str(screenshot_path)
        }
    except Exception as e:
        remove_state_file(state_file_path)
        print(f"API ERROR: using exported state for {session_id_for_log}: {e}")
        if context:
            await context.close()
        if browser and browser.is_connected():
            await browser.close()
        raise Exception(f"Could not use exported state for {session_id_for_log}: {str(e)}")
    finally:
        if context:
            await context.close()
        if browser and browser.is_connected():
            await browser.close()
        if pw_instance:
            await pw_instance.stop()
        