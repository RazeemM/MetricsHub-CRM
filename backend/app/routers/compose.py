"""One-to-one email written in the CRM (from a contact or an opportunity), sent through the CRM's mail system
(Microsoft 365 from the user's own mailbox, or SMTP) and logged on the timeline. No Outlook or mailto: needed."""
import datetime as dt
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from .. import mail
from ..crud import audit
from ..db import get_db
from ..models import Activity, Contact, Opportunity, User
from ..quotes import rich
from ..security import require_writer
from ..services import find_contact_by_email

router = APIRouter(prefix="/api/email", tags=["email"])
MAX_ATTACHMENTS = 10_000_000  # SMTP; Microsoft 365 allows 3 MB in total (checked when sending)
_email = TypeAdapter(EmailStr)


def _addresses(raw: str, field: str) -> list[str]:
    out = []
    for part in re.split(r"[,;\s]+", raw or ""):
        if not part:
            continue
        try:
            out.append(str(_email.validate_python(part)).lower())
        except ValidationError:
            raise HTTPException(422, f"{field}: '{part}' is not a valid email address") from None
    return list(dict.fromkeys(out))


@router.get("/compose")
def compose_info(contact_id: int | None = None, opportunity_id: int | None = None, db: Session = Depends(get_db),
                 user: User = Depends(require_writer)):
    """What the compose dialog needs: is sending set up, who it is sent as, the suggested recipient."""
    st = mail.status("transactional")
    contact = db.get(Contact, contact_id) if contact_id else None
    if not contact and opportunity_id and (opp := db.get(Opportunity, opportunity_id)):
        contact = opp.primary_contact
    return {
        "enabled": st["enabled"], "backend": st["backend"],
        "sender": mail.sender_for(user.email) if st["enabled"] else None,
        "reply_to": user.email if st["enabled"] and mail.sender_for(user.email) != user.email else None,
        "to": [contact.email] if contact and contact.email else [],
        "contact_id": contact.id if contact else None,
        "unsubscribed": bool(contact and contact.unsubscribed),
    }


@router.post("/send")
async def send_email(
    to: str = Form(...), cc: str = Form(""), bcc: str = Form(""), subject: str = Form(..., min_length=1, max_length=255),
    body: str = Form(..., min_length=1, max_length=50_000), contact_id: int | None = Form(None),
    opportunity_id: int | None = Form(None), files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db), user: User = Depends(require_writer),
):
    to_l, cc_l, bcc_l = _addresses(to, "To"), _addresses(cc, "Cc"), _addresses(bcc, "Bcc")
    if not to_l:
        raise HTTPException(422, "Add at least one recipient")
    if len(to_l) + len(cc_l) + len(bcc_l) > 50:
        raise HTTPException(422, "At most 50 recipients: use a campaign for bulk email")
    if not mail.status("transactional")["enabled"]:
        raise HTTPException(503, "Email sending is not configured on this server")
    attachments, total = [], 0
    for f in files:
        content = await f.read()
        total += len(content)
        if total > MAX_ATTACHMENTS:
            raise HTTPException(413, "Attachments are too large (10 MB in total)")
        attachments.append(mail.Attachment(f.filename or "attachment", content,
                                           f.content_type or "application/octet-stream"))

    contact = db.get(Contact, contact_id) if contact_id else find_contact_by_email(db, to_l[0])
    opp = db.get(Opportunity, opportunity_id) if opportunity_id else None
    sender = mail.sender_for(user.email)
    msg = mail.Message(
        sender=sender, to=to_l, cc=cc_l, bcc=bcc_l, subject=subject, text=body,
        html=f'<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px">{rich(body)}</div>',
        reply_to=user.email if sender != user.email else None, from_name=user.full_name,
        attachments=attachments)
    try:
        mail.send(msg)
    except mail.MailError as exc:
        raise mail.http_error(exc) from None

    names = ", ".join(a.name for a in attachments)
    db.add(Activity(
        type="email", subject=subject[:255], owner_id=user.id, created_by_id=user.id,
        contact_id=contact.id if contact else None,
        account_id=(contact.account_id if contact else None) or (opp.account_id if opp else None),
        opportunity_id=opp.id if opp else None, completed_at=dt.datetime.now(dt.UTC),
        body=(f"From {sender} to {', '.join(to_l + cc_l)}" + (f"\nAttachments: {names}" if names else "")
              + f"\n\n{body}")))
    audit(db, user, "email", contact.id if contact else 0, "send",
          {"to": to_l, "cc": cc_l, "bcc": bcc_l, "subject": subject, "attachments": names or None,
           "opportunity_id": opp.id if opp else None})
    db.commit()
    return {"sent": True, "sender": sender, "recipients": len(to_l) + len(cc_l) + len(bcc_l)}
