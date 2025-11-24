import datetime
from typing import Any, Dict, List, Optional

from a2a.types import AgentCard as A2AAgentCard
from a2a.types import AgentCapabilities, AgentSkill
from pydantic import BaseModel, Field


class Dependency(BaseModel):
    id: str
    version: str


class Lineage(BaseModel):
    dependencies: List[Dependency] = Field(default_factory=list)


class LLMConfig(BaseModel):
    provider: str
    model: str
    config: Dict[str, Any] = Field(default_factory=dict)


class Environment(BaseModel):
    container_image: Optional[str] = None
    env_vars: List[str] = Field(default_factory=list)


class Runtime(BaseModel):
    llm: Optional[LLMConfig] = None
    environment: Optional[Environment] = None


class EvalPack(BaseModel):
    name: str
    runner: str
    data_source: str
    runner_source: Optional[str] = None


class Evaluation(BaseModel):
    eval_packs: List[EvalPack] = Field(default_factory=list)

# We extend the A2A AgentCard to include our custom fields (lineage, runtime, evaluation)
# These aren't in the base A2A spec, so we'll create a "ExtendedAgentCard" that *contains* or *inherits*
# For now, to avoid breaking changes in our codebase, we will use composition or 
# try to map our fields to the A2A card if possible.
# A2A Card is strict Pydantic model.

# The user asked to "import the A2A SDK and fix it". 
# Let's redefine our AgentCard to *be* compliant or compatible.

class ExtendedAgentCard(A2AAgentCard):
    # A2A AgentCard has: name, description, version, url, capabilities, skills, defaultInputModes, defaultOutputModes
    # Our extras:
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    lineage: Optional[Lineage] = None
    runtime: Optional[Runtime] = None
    evaluation: Optional[Evaluation] = None
    
    # We need to map our 'interface.tools' to 'skills' in A2A
    # This mapping logic should happen during construction/generation.

# For backward compatibility with our just-written tests and code, we'll alias it
AgentCard = ExtendedAgentCard
