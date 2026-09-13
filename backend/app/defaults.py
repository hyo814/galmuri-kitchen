from .models import StorageLocation, db

DEFAULT_LOCATIONS = [("냉장실", "fridge"), ("냉동실", "freezer"), ("실온", "room")]


def seed_user_defaults(user_id):
    """새 사용자에게 기본 보관 위치를 만든다. commit은 호출 측에서."""
    for order, (name, kind) in enumerate(DEFAULT_LOCATIONS):
        db.session.add(StorageLocation(user_id=user_id, name=name, kind=kind, sort_order=order))
