from pydantic import BaseModel,ConfigDict,Field

class ReleaseInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    release_id:str=Field(min_length=1,max_length=64,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    epsilon:float=Field(gt=0,le=1,allow_inf_nan=False)
