import datetime as dt

from pydantic import BaseModel, ConfigDict


class ReportPreviewOut(BaseModel):
    date: dt.date
    content: str
    messages: list[str]  # as split for the channel
    configured: bool
    report_time: str
    last_scheduled: dt.date | None


class DispatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_date: dt.date
    trigger: str
    status: str
    late: bool
    channel: str
    messages: int
    error: str | None
    created_at: dt.datetime
