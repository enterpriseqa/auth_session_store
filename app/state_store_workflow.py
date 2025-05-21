import asyncio
import json
import argparse
import time

from app.state_store_playwright import (UseStateBody, StartLoginBody,StoreStateBody,
    start_login_session_store_state, use_exported_state_and_validate_session)

async def process_login_task(task):
    """Processes a single login task through all API endpoints."""
    username = task.get("username")
    login_url_str = task.get("login_url")
    target_url_str = task.get("target_url")

    if not all([username, login_url_str]):
        print(
            f"Skipping invalid task (missing username, login_url): {task}")
        return
    if (target_url_str is None):
        target_url_str = login_url_str

    print(f"\n{'='*20} Processing Task for User: {username}, Login URL: {login_url_str} {'='*20}")

    # 1. /start-login
    start_login_payload = {"username": username, "login_url": login_url_str}
    await start_login_session_store_state(StartLoginBody.model_validate(start_login_payload))

    # 2. /use-exported-state-and-goto
    use_exported_payload = {
        "username": username,
        "login_url": login_url_str,
        "target_url": target_url_str,
        "expected_text_after_login": task.get("expected_text_after_login"),
        "expected_text_timeout_ms": task.get("expected_text_timeout_ms")
    }
    
    await use_exported_state_and_validate_session(UseStateBody.model_validate(use_exported_payload))
    time.sleep(1)

    print(f"\n{'='*20} Finished Task for User: {username}, Login URL: {login_url_str} {'='*20}")

async def validate_existing_session(task):
    username = task.get("username")
    login_url_str = task.get("login_url")
    target_url_str = task.get("target_url")
    
    if not all([username, login_url_str]):
        print(
            f"Skipping invalid task (missing username, login_url): {task}")
        return
    if (target_url_str is None):
        target_url_str = login_url_str
    
    use_exported_payload = {
        "username": username,
        "login_url": login_url_str,  # Identifies which state file to use
        "target_url": target_url_str,  # Where to navigate
        "expected_text_after_login": task.get("expected_text_after_login"),
        "expected_text_timeout_ms": task.get("expected_text_timeout_ms")
    }
    
    await use_exported_state_and_validate_session(UseStateBody.model_validate(use_exported_payload))
    time.sleep(1)


def main():
    parser = argparse.ArgumentParser(
        description="Client to run Playwright login automation tasks via FastAPI.")
    parser.add_argument("--task_file", help="task file contains login information like username and url is mandatory")
    parser.add_argument(
        "--validate-session",
        action="store_true",
        help="If present, validate an existing session instead of processing login and validation."
    )   
    args = parser.parse_args()

    try:
        with open(args.task_file, 'r') as f:
            task = json.load(f)
    except FileNotFoundError:
        print(f"Error: Tasks file not found at {args.task_file}")
        return
    except json.JSONDecodeError:
        print(
            f"Error: Could not decode JSON from {args.task_file}. Please check its format.")
        return
    except Exception as e:
        print(
            f"An unexpected error occurred while reading the tasks file: {e}")
        return

    if args.validate_session:
        asyncio.run(validate_existing_session(task))
    else:
        asyncio.run(process_login_task(task))
        print("\n------------------------------------------------------------\n")
    time.sleep(2)

if __name__ == "__main__":
    main()
