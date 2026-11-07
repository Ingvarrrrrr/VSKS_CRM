"""Pydantic-схемы для роутера publication_results.py.

ПРАВИЛО №5: компактный файл схем (< 100 строк).
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ResultsSyncRequest(BaseModel):
    registration_number: Optional[str] = None


class EnsurePubRequest(BaseModel):
    platform: Optional[str] = "roseltorg_rb"
    platform_number: Optional[str] = None


class ApplyWinnerRequest(BaseModel):
    apply_positions_prices: bool = True
    apply_accepted_alternatives: bool = True


class SaveResultsRequest(BaseModel):
    registration_number: Optional[str] = None
    notice_date: Optional[str] = None
    protocol_number: Optional[str] = None
    protocol_date: Optional[str] = None
    meeting_address: Optional[str] = None
    meeting_time: Optional[str] = None
    submission_deadline: Optional[str] = None
    commission_order_number: Optional[str] = None
    commission_order_date: Optional[str] = None
    commission_members: Optional[List[Dict[str, Any]]] = None
    applications: List[Dict[str, Any]] = []
