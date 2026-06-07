from app.core.supabase import supabase


class DB:

    # -------------------------
    # FEATURED PROJECTS
    # -------------------------
    @staticmethod
    def get_featured_projects():
        return supabase.table("featured_projects").select("*").execute()

    @staticmethod
    def insert_featured_project(data):
        return supabase.table("featured_projects").insert(data).execute()

    @staticmethod
    def update_featured_project(project_id, data):
        return supabase.table("featured_projects").update(data).eq("id", project_id).execute()

    @staticmethod
    def upsert_featured_project(data, key="slug"):
        return supabase.table("featured_projects").upsert(data, on_conflict=key).execute()


    # -------------------------
    # INSIGHT PROJECTS
    # -------------------------
    @staticmethod
    def get_insight_projects():
        return supabase.table("insight_projects").select("*").execute()

    @staticmethod
    def insert_insight_project(data):
        return supabase.table("insight_projects").insert(data).execute()

    @staticmethod
    def update_insight_project(project_id, data):
        return supabase.table("insight_projects").update(data).eq("id", project_id).execute()

    @staticmethod
    def upsert_insight_project(data, key="title"):
        return supabase.table("insight_projects").upsert(data, on_conflict=key).execute()