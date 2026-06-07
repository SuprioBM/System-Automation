from app.core.supabase import supabase

FEATURED_LIMIT = 4
INSIGHT_LIMIT = 6


class RankingEngine:

    # -------------------------
    # FETCH CURRENT STATE
    # -------------------------
    @staticmethod
    def get_featured():
        return supabase.table("featured_projects") \
            .select("*") \
            .order("score", desc=True) \
            .execute().data or []

    @staticmethod
    def get_insights():
        return supabase.table("insight_projects") \
            .select("*") \
            .order("score", desc=True) \
            .execute().data or []

    # -------------------------
    # MAIN ENTRY POINT
    # -------------------------
    @staticmethod
    def process_project(ai_result: dict):

        category = ai_result.get("category")
        score = float(ai_result.get("score", 0))

        # guard
        if category == "ignore" or score <= 0:
            return {"action": "ignored"}

        if category == "featured":
            return RankingEngine._handle_featured(ai_result)

        if category == "insight":
            return RankingEngine._handle_insight(ai_result)

        return {"action": "invalid_category"}

    # -------------------------
    # FEATURED LOGIC (TOP 4)
    # -------------------------
    @staticmethod
    def _handle_featured(project):

        featured = RankingEngine.get_featured()

        # insert if space exists
        if len(featured) < FEATURED_LIMIT:
            supabase.table("featured_projects").insert(project).execute()
            return {"action": "inserted", "table": "featured"}

        # find weakest
        lowest = min(featured, key=lambda x: x.get("score", 0))

        # replace only if strictly better
        if float(project["score"]) > float(lowest["score"]):

            supabase.table("featured_projects") \
                .delete() \
                .eq("id", lowest["id"]) \
                .execute()

            supabase.table("featured_projects") \
                .insert(project) \
                .execute()

            return {
                "action": "replaced",
                "removed": lowest.get("title")
            }

        return {"action": "rejected_not_strong_enough"}

    # -------------------------
    # INSIGHT LOGIC (TOP 6)
    # -------------------------
    @staticmethod
    def _handle_insight(project):

        insights = RankingEngine.get_insights()

        if len(insights) < INSIGHT_LIMIT:
            supabase.table("insight_projects").insert(project).execute()
            return {"action": "inserted", "table": "insight"}

        lowest = min(insights, key=lambda x: x.get("score", 0))

        if float(project["score"]) > float(lowest["score"]):

            supabase.table("insight_projects") \
                .delete() \
                .eq("id", lowest["id"]) \
                .execute()

            supabase.table("insight_projects") \
                .insert(project) \
                .execute()

            return {
                "action": "replaced",
                "removed": lowest.get("title")
            }

        return {"action": "rejected_not_strong_enough"}