from flask import Blueprint, request, redirect, url_for, render_template, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime

from app.extensions import db
from app.constants.enums import UserRoleEnum  # this enum is safe to import
from app.utils.decorators import role_required
    
comm_bp = Blueprint("comm_bp", __name__, url_prefix="/comm")


def _add_participants(conv, user_ids, can_post=True, role="member"):
    """Add users to a conversation, ignoring existing participants.
    Note: conv must be flushed so conv.id exists if called right after creation."""
    # lazy-import model to avoid circular imports at module import time
    from app.models import ConversationParticipant

    existing = {p.user_id for p in conv.participants.all()} if getattr(conv, "participants", None) is not None else set()
    added = 0
    for uid in user_ids:
        if uid in existing:
            continue
        db.session.add(
            ConversationParticipant(
                conversation_id=conv.id, user_id=uid, can_post=can_post, role=role
            )
        )
        added += 1
    return added


def _fanout_receipts(msg):
    """Create MessageReceipt entries for all conversation participants except sender."""
    # lazy import
    from app.models import MessageReceipt

    # prefer participants relationship on conversation
    part_ids = []
    try:
        part_ids = [p.user_id for p in msg.conversation.participants.all() if p.user_id != msg.sender_id]
    except Exception:
        # fallback: no participants available (shouldn't happen under normal flow)
        part_ids = []

    for uid in part_ids:
        db.session.add(MessageReceipt(message_id=msg.id, user_id=uid))


@comm_bp.route("/start", methods=["POST"])
@login_required
def start_conversation():
    """Start a direct or group conversation."""
    title = ""
    if request.is_json:
        title = request.json.get("title") or ""
        raw_ids = request.json.get("participant_ids") or ""
    else:
        title = request.form.get("title") or ""
        raw_ids = request.form.get("participant_ids") or ""

    try:
        ids = [int(x) for x in str(raw_ids).split(",") if str(x).strip().isdigit()]
    except Exception:
        ids = []

    # include the creator
    if current_user.id not in ids:
        ids.append(current_user.id)

    is_group = len(set(ids)) > 2

    # lazy imports
    from app.models import Conversation

    conv = Conversation(
        created_by=current_user.id,
        title=title or None,
        is_group=is_group,
        is_broadcast=False,
    )
    try:
        db.session.add(conv)
        db.session.flush()  # get conv.id
        _add_participants(
            conv,
            ids,
            can_post=True,
            role="admin" if current_user.id in ids else "member",
        )
        db.session.commit()
        flash("Conversation created.", "success")
        return redirect(url_for("comm_bp.view_conversation", conversation_id=conv.id))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("[comm.start_conversation] failed")
        flash("Could not create conversation.", "danger")
        return redirect(url_for("comm_bp.inbox"))


@comm_bp.route("/<int:conversation_id>/send", methods=["POST"])
@login_required
def send_message(conversation_id):
    """Send a message in a conversation."""
    from app.models import Conversation, ConversationParticipant, Message

    conv = Conversation.query.get_or_404(conversation_id)
    part = ConversationParticipant.query.filter_by(conversation_id=conv.id, user_id=current_user.id).first()
    if not part:
        flash("You are not a participant.", "danger")
        return redirect(url_for("comm_bp.inbox"))
    if not part.can_post:
        flash("Posting is disabled for you in this conversation.", "danger")
        return redirect(url_for("comm_bp.view_conversation", conversation_id=conv.id))

    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Message cannot be empty.", "warning")
        return redirect(url_for("comm_bp.view_conversation", conversation_id=conv.id))

    try:
        # IMPORTANT: Message model field is 'content' in your schema
        msg = Message(conversation_id=conv.id, sender_id=current_user.id, content=body)
        db.session.add(msg)
        db.session.flush()
        _fanout_receipts(msg)
        db.session.commit()
        return redirect(url_for("comm_bp.view_conversation", conversation_id=conv.id))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("[comm.send_message] failed")
        flash("Could not send message.", "danger")
        return redirect(url_for("comm_bp.view_conversation", conversation_id=conv.id))


@comm_bp.route("/inbox")
@login_required
def inbox():
    """List conversations the user belongs to with unread counts."""
    from app.models import Conversation, ConversationParticipant, Message, MessageReceipt

    convs = (
        Conversation.query.join(
            ConversationParticipant,
            ConversationParticipant.conversation_id == Conversation.id,
        )
        .filter(ConversationParticipant.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )

    unread_map = {}
    if convs:
        conv_ids = [c.id for c in convs]
        rows = (
            db.session.query(
                Message.conversation_id, func.count(MessageReceipt.message_id)
            )
            .join(MessageReceipt, MessageReceipt.message_id == Message.id)
            .filter(
                Message.conversation_id.in_(conv_ids),
                MessageReceipt.user_id == current_user.id,
                # use the model's field name 'is_read'
                MessageReceipt.is_read.is_(False),
            )
            .group_by(Message.conversation_id)
            .all()
        )
        unread_map = {cid: cnt for cid, cnt in rows}

    return render_template("comm/inbox.html", conversations=convs, unread_map=unread_map)


@comm_bp.route("/<int:conversation_id>")
@login_required
def view_conversation(conversation_id):
    """View messages in a conversation."""
    from app.models import Conversation, ConversationParticipant, Message, MessageReceipt

    conv = Conversation.query.get_or_404(conversation_id)
    if not ConversationParticipant.query.filter_by(conversation_id=conv.id, user_id=current_user.id).first():
        flash("You are not a participant.", "danger")
        return redirect(url_for("comm_bp.inbox"))

    messages = conv.messages.order_by(Message.created_at.asc()).all()

    # mark unread as read (use is_read)
    try:
        (
            MessageReceipt.query.join(Message, Message.id == MessageReceipt.message_id)
            .filter(
                Message.conversation_id == conv.id,
                MessageReceipt.user_id == current_user.id,
                MessageReceipt.is_read.is_(False),
            )
            .update({"is_read": True, "read_at": datetime.utcnow()}, synchronize_session=False)
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("[comm.view_conversation] couldn't mark receipts")

    return render_template("comm/conversation.html", conversation=conv, messages=messages)


@comm_bp.route("/broadcast", methods=["POST"])
@login_required
def broadcast():
    """
    Broadcast message according to user role:
      - Admin/Patient: to any users they select (security settings enforced elsewhere)
      - Enterprise: to followers only
    POST:
      - title (optional)
      - target_user_ids: comma-separated user ids
      - body: message
    """
    from app.models import Conversation, Message, ConversationParticipant, FavoriteEnterprise, User

    title = (request.form.get("title") or "").strip() or None
    body = (request.form.get("body") or "").strip()
    raw = (request.form.get("target_user_ids") or "").strip()

    ids = [int(x) for x in raw.split(",") if x.strip().isdigit()]

    # Robust enterprise role detection (handles enum or string)
    cur_role = getattr(current_user, "role", None)
    is_enterprise = (cur_role == UserRoleEnum.ENTERPRISE) or (isinstance(cur_role, str) and cur_role.lower().startswith("enter"))

    # Apply enterprise restriction: only followers
    if is_enterprise:
        try:
            followers = {f.user_id for f in FavoriteEnterprise.query.filter_by(enterprise_id=current_user.id).all()}
            ids = [uid for uid in ids if uid in followers]
        except Exception:
            current_app.logger.exception("[comm.broadcast] failed to load followers")
            ids = []

    if not ids:
        flash("No recipients available for broadcast.", "warning")
        return redirect(url_for("comm_bp.inbox"))
    if not body:
        flash("Message cannot be empty.", "warning")
        return redirect(url_for("comm_bp.inbox"))

    try:
        conv = Conversation(
            created_by=current_user.id,
            title=title,
            is_group=True,
            is_broadcast=True,
        )
        db.session.add(conv)
        db.session.flush()

        # creator can post; recipients cannot
        _add_participants(conv, [current_user.id], can_post=True, role="admin")
        _add_participants(conv, ids, can_post=False, role="member")
        db.session.flush()

        # Message model field is 'content'
        msg = Message(conversation_id=conv.id, sender_id=current_user.id, content=body)
        db.session.add(msg)
        db.session.flush()
        _fanout_receipts(msg)
        db.session.commit()

        flash(f"Broadcast sent to {len(ids)} users.", "success")
        return redirect(url_for("comm_bp.view_conversation", conversation_id=conv.id))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("[comm.broadcast] failed")
        flash("Could not send broadcast.", "danger")
        return redirect(url_for("comm_bp.inbox"))


