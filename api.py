from flask import Blueprint, jsonify, request, flash, redirect, url_for
from models import db, User, Product, Expense, Sale, SyncMeta
from datetime import datetime
import requests
import pprint

api = Blueprint("api", __name__)

# ------------------------------------------------------------------
# Helper utilities
# ------------------------------------------------------------------

MODEL_MAP = {
    "User":    User,
    "Product": Product,
    "Expense": Expense,
    "Sale":    Sale,
}

# Map model names to plural endpoint names to match server API routes
ENDPOINT_MAP = {
    "User": "users",
    "Product": "products",
    "Expense": "expenses",
    "Sale": "sales",
}

def model_to_dict(obj):
    """
    Return a JSON-serialisable dict for any of our 4 models.
    Only include columns that actually exist.
    """
    d = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    # convert datetimes to ISO strings
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def dict_to_model(model_cls, data):
    """
    Create a *new* model instance from the JSON payload (used on pull).
    """
    kwargs = {}
    for col in model_cls.__table__.columns:
        name = col.name
        if name in data:
            val = data[name]
            if isinstance(col.type.python_type, type) and col.type.python_type is datetime:
                val = datetime.fromisoformat(val)
            kwargs[name] = val
    return model_cls(**kwargs)


def get_last_sync(model_name):
    meta = SyncMeta.query.filter_by(model_name=model_name).first()
    return meta.last_sync if meta else datetime(2000, 1, 1)


def set_last_sync(model_name, ts):
    meta = SyncMeta.query.filter_by(model_name=model_name).first()
    if meta is None:
        meta = SyncMeta(model_name=model_name, last_sync=ts)
        db.session.add(meta)
    else:
        meta.last_sync = ts
    db.session.commit()


# ------------------------------------------------------------------
# 1. PUSH unsynced records TO server
# ------------------------------------------------------------------
@api.route("/sync/push", methods=["GET", "POST"])
def push_all():
    """
    Push unsynced *or* modified rows to the remote server.
    """
    SERVER = "http://localhost:5001/api/sync"
    overall_errors = {}

    for model_name, model_cls in MODEL_MAP.items():
        last_sync = get_last_sync(model_name)
        # Fetch records that are either:
        # - Never synced (synced=False)
        # - OR modified after last sync
        modified_rows = model_cls.query.filter(
            (model_cls.synced == False) | (model_cls.last_modified > last_sync)
        ).all()

        if not modified_rows:
            continue

        payload = [model_to_dict(row) for row in modified_rows]

        try:
            r = requests.post(f"{SERVER}/{ENDPOINT_MAP[model_name]}", json=payload, timeout=10)
            r.raise_for_status()
        except Exception as e:
            overall_errors[model_name] = str(e)
            continue

        # If successful, mark all as synced
        for row in modified_rows:
            row.synced = True
        db.session.commit()

        # Update sync timestamp
        set_last_sync(model_name, datetime.utcnow())

    if overall_errors:
        return jsonify({"message": "Push finished with errors", "details": overall_errors}), 207
    return jsonify({"message": "Push completed"})


# ------------------------------------------------------------------
# 2. PULL remote changes SINCE last sync
# ------------------------------------------------------------------

@api.route("/sync/pull", methods=["GET", "POST"])
def pull_all():
    SERVER = "http://localhost:5001/api/sync"
    overall_errors = {}

    for model_name, model_cls in MODEL_MAP.items():
        since = get_last_sync(model_name).isoformat()
        try:
            r = requests.get(f"{SERVER}/{ENDPOINT_MAP[model_name]}", params={"since": since}, timeout=10)
            r.raise_for_status()
            remote_rows = r.json()
        except Exception as e:
            overall_errors[model_name] = str(e)
            continue
        pp = pprint.PrettyPrinter(indent=2)

        if model_name == "Sale":
            pp.pprint(model_cls)  # or print(json.dumps(payload, indent=2))

        changes = False
        for data in remote_rows:
            row = model_cls.query.filter_by(uuid=data["uuid"]).first()
            remote_lm = datetime.fromisoformat(data["last_modified"])

            if row:
                if remote_lm > row.last_modified:
                    for col in model_cls.__table__.columns:
                        name = col.name
                        if name in data:
                            val = data[name]
                            if isinstance(col.type.python_type, type) and col.type.python_type is datetime:
                                val = datetime.fromisoformat(val)
                            setattr(row, name, val)
                    changes = True
            else:
                # Check for potential uniqueness conflicts before insert
                try:
                    conflict = None
                    if model_name == "User":
                        if "email" in data:
                            conflict = model_cls.query.filter_by(email=data["email"]).first()
                        if not conflict and "username" in data:
                            conflict = model_cls.query.filter_by(username=data["username"]).first()

                    if conflict:
                        # Skip insert if conflict exists
                        continue

                    new_obj = dict_to_model(model_cls, data)
                    db.session.add(new_obj)
                    changes = True

                except Exception as e:
                    overall_errors.setdefault(model_name, []).append(str(e))
                    continue

        if changes:
            db.session.commit()
            set_last_sync(model_name, datetime.utcnow())

    if overall_errors:
        return jsonify({"message": "Pull finished with errors", "details": overall_errors}), 207
    return jsonify({"message": "Pull completed"})

"""
@api.route("/sync/full", methods=["GET", "POST"])
def sync_full():
    # Push local unsynced data to remote server
    push_response = push_all()
    if push_response.status_code != 200:
        #return jsonify({"message": "Push failed", "details": push_response.get_json()}), 500
        flash("❌ Sync failed during push: {}".format(push_response.get_json().get("message", "Unknown error")), "danger")
        return redirect(url_for('backup.backup_page'))

    # Pull remote updates since last sync
    pull_response = pull_all()
    if pull_response.status_code not in [200, 207]:
        #return jsonify({"message": "Pull failed", "details": pull_response.get_json()}), 500
        flash("❌ Sync failed during pull: {}".format(pull_response.get_json().get("message", "Unknown error")), "danger")
        return redirect(url_for('backup.backup_page'))

    #return jsonify({"message": "Full sync completed"}), 200
    flash("✅ Full sync completed successfully!", "success")
    return redirect(url_for('backup.backup_page'))
"""

from flask import flash, redirect, url_for
import requests

@api.route("/sync/full", methods=["GET", "POST"])
def sync_full():
    try:
        # Push local unsynced data to remote server
        push_response = push_all()
        if isinstance(push_response, tuple):
            push_response, push_status = push_response
        else:
            push_status = push_response.status_code

        if push_status != 200:
            flash("❌ Sync failed during push: {}".format(getattr(push_response, 'message', 'Server error')), "danger")
            return redirect(url_for('backup.backup_page'))

        # Pull remote updates since last sync
        pull_response = pull_all()
        if isinstance(pull_response, tuple):
            pull_response, pull_status = pull_response
        else:
            pull_status = pull_response.status_code

        if pull_status not in [200, 207]:
            flash("❌ Sync failed during pull: {}".format(getattr(pull_response, 'message', 'Server error')), "danger")
            return redirect(url_for('backup.backup_page'))

    except requests.exceptions.ConnectionError:
        flash("❌ No internet connection. Please check your network and try again.", "danger")
        return redirect(url_for('backup.backup_page'))

    except Exception as e:
        flash("❌ An unexpected error occurred during sync: {}".format(str(e)), "danger")
        return redirect(url_for('backup.backup_page'))

    flash("✅ Full sync completed successfully!", "success")
    return redirect(url_for('backup.backup_page'))


