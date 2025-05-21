import dataclasses
from pydantic import BaseModel, ConfigDict
from dataclasses import dataclass, field


@dataclass
class StepResult:
    def __init__(
            self,
            action: str, is_done: bool = False, result=''):
        self.result = result
        self.action = action
        self.is_done = is_done


class AgentBrain(BaseModel):
    """Current state of the agent"""

    memory: str
    next_goal: str

class AgentOutput(BaseModel):
    """Output model for agent
    @dev note: this model is extended with custom actions in AgentService. You can also use some fields that are not in this model as provided by the linter, as long as they are registered in the DynamicActions model.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    extracted_text: str
    accuracy_statistics_summary: str
