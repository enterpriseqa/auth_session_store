import base64
import json
import logging
import os
import random
import re
import string
import time
from functools import wraps
from typing import Any, Callable, Coroutine, ParamSpec, TypeVar
from typing import Any, Dict, List

from playwright.async_api import Page

from app.utils.qa_logging import log_message
# from views import AgentOutput

# Define generic type variables for return type and parameters
R = TypeVar('R')
P = ParamSpec('P')


def get_max_steps():
    return 10


def time_execution_sync(additional_text: str = '') -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            log_message(
                f'{additional_text} Execution time: {execution_time:.2f} seconds')
            return result

        return wrapper

    return decorator


def time_execution_async(
        additional_text: str = '',
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            log_message(
                f'{additional_text} Execution time: {execution_time:.2f} seconds')
            return result

        return wrapper

    return decorator


def singleton(cls):
    instance = [None]

    def wrapper(*args, **kwargs):
        if instance[0] is None:
            instance[0] = cls(*args, **kwargs)
        return instance[0]

    return wrapper


def read_json_file(file_path) -> Dict[str, any]:  # type: ignore
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)  # Load the JSON data into a Python dictionary
        return data
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None  # type: ignore
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in {file_path}")
        return None  # type: ignore
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None  # type: ignore


'''
def parse_json_string(txt_file_path) -> AgentOutput | None:
    try:
        # Read the .txt file
        with open(txt_file_path, 'r', encoding='utf-8') as txt_file:
            txt_content = txt_file.read()
            data = json.loads(txt_content)
            parsed: AgentOutput = AgentOutput.model_validate_json(
                json.dumps(data))
            print(parsed)
            return parsed
    except FileNotFoundError:
        print(f"Error: .txt file not found at {txt_file_path}")
        return None
    except Exception as e:
        print(f"Error reading .txt file: {e}")
        return None
'''


async def remove_highlights(page: Page):
    """
    Removes all highlight overlays and labels created by the highlightElement function.
    Handles cases where the page might be closed or inaccessible.
    """
    try:
        await page.evaluate(
            """
	try {
		// Remove the highlight container and all its contents
		const container = document.getElementById('playwright-highlight-container');
		if (container) {
			container.remove();
		}

		// Remove highlight attributes from elements
		const highlightedElements = document.querySelectorAll('[browser-user-highlight-id^="playwright-highlight-"]');
		highlightedElements.forEach(el => {
			el.removeAttribute('browser-user-highlight-id');
		});
	} catch (e) {
		console.error('Failed to remove highlights:', e);
	}
	"""
        )
        await page.evaluate(
            """
	try {
		const highlightedSpans = document.querySelectorAll('span#playwright-highlighted-text')
		highlightedSpans.forEach(span => {
			const parent = span.parentNode;
			parent.replaceChild(
				document.createTextNode(span.innerText), span);
			parent.normalize();
		});
	} catch (e) {
		console.error('Failed to remove highlights:', e);
	}
	"""
        )
    except Exception as e:
        # Don't raise the error since this is not critical functionality
        pass
        # endregion


async def get_page_screenshot(page, path: str) -> any:  # type: ignore
    try:
        screen_shot = await page.screenshot()
        await page.screenshot(path=path)
        screenshot_b64 = base64.b64encode(screen_shot).decode('utf-8')
        return screenshot_b64
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def read_file_to_string(filename):
    try:
        with open(filename, 'r') as file:
            return file.read()
    except IOError:
        return None


def parse_content_pairs(text) -> Dict[str, str]:
    """
    Parses a string containing lines of the format 'number[:]<content>' and
    returns a list of tuples, where each tuple contains the number and the content,
    handling multi-line content.

    Args:
        text: A string containing the lines to parse.

    Returns:
        A list of tuples, where each tuple is (number, content).
    """
    pairs: Dict[str, str] = {}
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        match = re.match(r'(\d+)\[:\]\s*(.*)', lines[i])
        if match:
            number = match.group(1)
            content = match.group(2).strip()
            i += 1
            while i < len(lines):
                next_match = re.match(r'\d+\[:\]\s*(.*)', lines[i])
                if next_match:
                    break  # new line with number found, break and move to next line
                else:
                    # multi line content is added to existing content
                    content += "\n" + lines[i].strip()
                    i += 1
            pairs[number] = content
        else:
            i += 1  # Skip non-matching lines

    return pairs


def load_html_content_files(folder_path, step_index):
    clickable_elements: Dict[str, str] = {}

    if not os.path.isdir(folder_path):
        print(f"Error: Folder '{folder_path}' not found.")
        return clickable_elements

    try:
        path_pattern = f"interactive_elements_{step_index}"
        files_in_folder = os.listdir(folder_path)
        html_content_files = [
            filename for filename in files_in_folder if path_pattern in filename.lower()]
        html_content_files.sort()
        for html_content_file in html_content_files:
            file_path = os.path.join(folder_path, html_content_file)
            content = read_file_to_string(file_path)
            if (content != None):
                content_paris = parse_content_pairs(content)
                clickable_elements = content_paris
            else:
                clickable_elements = {}

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return clickable_elements


def load_json_as_string(fileName):
    try:
        cwd = os.getcwd()  # Get the current working directory
        filepath = os.path.join(cwd, fileName)  # Construct the full file path
        with open(filepath, 'r') as f:
            json_string = f.read()  # Read the entire file into a string
            return json_string
    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
        return None
    except Exception as e:
        print(f"Error loading JSON: {e}")
    return None


def generate_random_prefix(length=8):
    """Generates a random string of characters and digits for a filename prefix."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))
