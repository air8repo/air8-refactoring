"""Run a local browser-test server with deterministic in-memory data.

This entry point is for local visual and interaction verification only. It does
not replace the production application configuration and does not connect to
MongoDB.
"""

from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from flask import redirect, url_for
from flask_login import UserMixin, login_user

from backend.app import create_app
from backend.app.config import config_by_name
from backend.app.extensions import login_manager
from backend.app.routes import main as main_routes


class BrowserTestUser(UserMixin):
    id = "browser-test-user"
    username = "browser-test-user"


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = documents or []

    def count_documents(self, _query):
        return len(self.documents)

    def find(self, _query=None):
        return list(self.documents)


class FakeMongo:
    def __init__(self):
        self.refactoring_financing_order = FakeCollection()
        self.refactoring_repayment_order = FakeCollection()
        self.refactoring_bank_statement = FakeCollection()
        self.refactoring_financing_overview = FakeCollection(
            [
                {
                    "refactoring_status": "Loan booked",
                    "loan_submission_batch": 1,
                    "bank_statements": [
                        {
                            "start_date": datetime(2026, 1, 15),
                            "finance_amount": 100,
                            "interest_amount_usd": 10,
                        }
                    ],
                },
                {
                    "refactoring_status": "Loan booked",
                    "loan_submission_batch": 2,
                    "bank_statements": [
                        {
                            "start_date": datetime(2026, 1, 20),
                            "finance_amount": 300,
                            "interest_amount_usd": 30,
                        }
                    ],
                },
                {
                    "refactoring_status": "Loan booked",
                    "loan_submission_batch": 3,
                    "bank_statements": [
                        {
                            "start_date": datetime(2026, 3, 20),
                            "finance_amount": 310,
                            "interest_amount_usd": 35,
                        }
                    ],
                },
            ]
        )


def create_browser_test_app():
    app = create_app(config_by_name["test"])
    fake_mongo = FakeMongo()

    # Keep the real dashboard route and template; replace only its data seam.
    main_routes.get_mongo = lambda: fake_mongo
    login_manager.user_loader(lambda _user_id: BrowserTestUser())

    @app.get("/__browser_test_login")
    def browser_test_login():
        login_user(BrowserTestUser())
        return redirect(url_for("main.dashboard"))

    return app


if __name__ == "__main__":
    create_browser_test_app().run(
        host="127.0.0.1",
        port=5001,
        debug=False,
        use_reloader=False,
    )
