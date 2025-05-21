# Auth Session Storage Client

This script provides a command-line interface to automate website login processes and validate active sessions. It leverages a backend module (`app.state_store_playwright`) that presumably uses Playwright to interact with web pages, store browser state (cookies, local storage), and reuse this state for subsequent session validations.

The script can perform two main operations:
1.  **Full Login and State Storage:** Initiates a login sequence, allows for manual login completion (if required by the backend), stores the authenticated browser state, and then validates the session.
2.  **Session Validation Only:** Uses previously stored browser state to navigate to a target URL and validate an existing session.

## Features

*   Automates login sequences via a task definition file.
*   Stores authenticated browser state for reuse.
*   Validates active sessions using stored state.
*   Configurable via a JSON task file.
*   Command-line interface for easy execution.

## Prerequisites

*   Python 3.7+ (due to `asyncio` and type hinting usage)
*   The `app.state_store_playwright` module and its dependencies. This module is expected to contain:
    *   `start_login_session_store_state`: A function to initiate login, potentially open a browser for manual interaction, and then store the browser's state (cookies, local storage, etc.) associated with a username and login URL.
    *   `use_exported_state_and_validate_session`: A function to load a previously stored browser state, navigate to a target URL, and optionally check for specific text to validate the session.
    *   Pydantic models: `UseStateBody`, `StartLoginBody` for data validation.
*   Dependencies for `app.state_store_playwright` likely include:
    *   `playwright`
    *   `pydantic`
*   Playwright browsers installed (`playwright install`)

## Setup

1.  **Clone the repository (if applicable) or ensure you have this script and the `app` directory.**
2.  **Install dependencies:**
    Create a `requirements.txt` file with at least:
    ```
    # requirements.txt
    # Add playwright and pydantic if not already managed by app.state_store_playwright
    # playwright
    # pydantic
    ```
    Then run:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: If `app.state_store_playwright` has its own setup, follow its instructions.*

3.  **Install Playwright browsers (if not already done by the `app` module's setup):**
    ```bash
    playwright install
    ```

## Task File Format

The script requires a JSON task file (`--task_file`) to define the login parameters. The structure is as follows:

```json
{
  "username": "your_username",
  "login_url": "https://example.com/login",
  "target_url": "https://example.com/dashboard",
  "expected_text_after_login": "Welcome, your_username!",
  "expected_text_timeout_ms": 10000
}```

## Environment Variables

```STATE_STORAGE_DIR="Storage directory where the session details are stored",
   X_API_KEY="API key created from www.qaagent.ai website for validating the successful login using OCR AI model",
   OCR_AGENT_BASE_URL=https://www.qaagent.ai
```


