"""Regression test for delete-cascade behavior on Postgres and SQLite alike.

users.id -> ondelete=CASCADE on storage_locations/ingredients/staples/item_rules,
but ingredients.location_id -> storage_locations has no ondelete (NO ACTION on
Postgres). Deleting a user must still succeed and remove everything, since
both the location and the ingredient rows are cascade-deleted as part of the
same statement.
"""

from datetime import date

from app.models import Ingredient, ItemRule, StorageLocation, Staple, User, db


def test_deleting_user_cascades_to_all_owned_rows(app):
    with app.app_context():
        user = User(provider="test", provider_id="cascade", nickname="u")
        db.session.add(user)
        db.session.commit()

        location = StorageLocation(user_id=user.id, name="냉장실", kind="fridge")
        db.session.add(location)
        db.session.commit()

        db.session.add(
            Ingredient(
                user_id=user.id,
                location_id=location.id,
                name="우유",
                purchased_on=date(2026, 9, 1),
            )
        )
        db.session.add(Staple(user_id=user.id, name="소금"))
        db.session.add(ItemRule(user_id=user.id, keyword="계란", warn_days=25, danger_days=30))
        db.session.commit()

        user_id = user.id
        db.session.delete(user)
        db.session.commit()

        assert db.session.get(User, user_id) is None
        assert StorageLocation.query.filter_by(user_id=user_id).count() == 0
        assert Ingredient.query.filter_by(user_id=user_id).count() == 0
        assert Staple.query.filter_by(user_id=user_id).count() == 0
        assert ItemRule.query.filter_by(user_id=user_id).count() == 0
