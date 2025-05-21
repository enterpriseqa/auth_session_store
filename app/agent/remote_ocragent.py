from asyncio import sleep
from enum import Enum
import json
import logging
from numbers import Number
import threading
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel
from app.agent.views import AgentOutput
from langchain_core.runnables import Runnable

from app.utils.qa_logging import log_message, set_thread_context_id
from app.utils.utils import generate_random_prefix


class TaskId(BaseModel):
    task_id: str


class TaskStatus(str, Enum):
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class LLMCallRecordBase(BaseModel):
    taskId: str
    requestId: str
    status: TaskStatus
    data: Optional[str] = None  # JSON data from AI model output as string


class LLMCallRecordCreate(LLMCallRecordBase):
    status: TaskStatus = TaskStatus.STARTED  # Default for creation


class LLMCallRecordInDB(LLMCallRecordBase):
    # If you want to include MongoDB's _id, you can add it here
    # id: Optional[str] = Field(None, alias="_id") # Example if using ObjectId as str
    pass


class RemoteOCRLLM(Runnable):
    def __init__(self, api_key: str, api_endpoint: str, **data: Any):
        self.api_key = api_key
        self.api_endpoint = api_endpoint
        self._client = None
        super().__init__(**data)
        if self._client is None:
            self._client = httpx.AsyncClient()

    async def ainvoke(self, screenshot, text_to_search: str) -> AgentOutput:
        request_id = f"{generate_random_prefix(10)}"
        context_id = f"{request_id}-{threading.get_native_id()}"
        
        set_thread_context_id(context_id)
        payload = {
            "request_id": request_id,
            "text_to_search": text_to_search,
            "screenshot": screenshot
        }
        headers = {}
        headers['x-api-key'] = self.api_key
        headers['Content-Type'] = "application/json"

        try:
            # THE KEY PART: await the async HTTP call
            response = await self._client.request("POST", f"{self.api_endpoint}/ocr-agent/search_text",
                                                  json=payload,
                                                  headers=headers,
                                                  timeout=120
                                                  )
            response.raise_for_status()
        except httpx.RequestError as e:
            # Handle network errors
            log_message(f"Request Error from llm call:{e}", logging.ERROR)
            raise ConnectionError(f"Error connecting to LLM API: {e}") from e
        except httpx.HTTPStatusError as e:
            # Handle API errors (4xx, 5xx)
            log_message(f"HttpStatus Error from llm call:{e}", logging.ERROR)
            raise ValueError(
                f"LLM API Error: {e.response.status_code} - {e.response.text}") from e

        parsed: TaskId = TaskId.model_validate(
            json.loads(response.json()))
        ocr_response: str | None = await self.check_process_ocr_status(parsed.task_id, request_id)

        if ocr_response == None:
            raise ValueError("new Invalid response")
        return AgentOutput.model_validate(json.loads(ocr_response))

    async def check_process_ocr_status(self, taskId: str, requestId: str):
        headers = {}
        headers['x-api-key'] = self.api_key
        headers['Content-Type'] = "application/json"
        ocr_response = None
        while (True):
            try:
                response = await self._client.request("GET", f"{self.api_endpoint}/ocr-agent/llm-call-status/{requestId}/{taskId}",
                                                      headers=headers)
                response.raise_for_status()  # Check for HTTP errors
            except httpx.RequestError as e:
                # Handle network errors
                raise ConnectionError(
                    f"Error connecting to LLM API: {e}") from e
            except httpx.HTTPStatusError as e:
                # Handle API errors (4xx, 5xx)
                raise ValueError(
                    f"LLM API Error: {e.response.status_code} - {e.response.text}") from e

            parsed: LLMCallRecordInDB = LLMCallRecordInDB.model_validate(
                response.json())
            await sleep(10)
            if (parsed.status == 'SUCCESS' or parsed.status == 'FAILED'):
                if (parsed.status == 'SUCCESS'):
                    ocr_response = parsed.data
                return ocr_response

    # type: ignore

    async def invoke(self, step: int, screenshot, step_details: Dict[str, Any], interactive_elements: str) -> AgentOutput:
        pass
