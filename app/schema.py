from app.db import run_query


def apply_constraints() -> None:
    run_query("CREATE CONSTRAINT term_name_unique IF NOT EXISTS FOR (t:Term) REQUIRE t.name IS UNIQUE")
    run_query("CREATE CONSTRAINT category_name_unique IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE")
    run_query("CREATE CONSTRAINT user_email_unique IF NOT EXISTS FOR (u:User) REQUIRE u.email IS UNIQUE")
