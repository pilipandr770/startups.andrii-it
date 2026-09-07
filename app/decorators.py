from functools import wraps
from flask import abort
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def superadmin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper
