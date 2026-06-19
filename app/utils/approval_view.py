import discord


class ApprovalView(discord.ui.View):
    def __init__(self, draft_id: str | None = None, draft_type: str | None = None):
        super().__init__(timeout=None)

        self.draft_id = draft_id
        self.draft_type = draft_type

        print("🧩 View initialized for draft:", draft_id, "type:", draft_type)

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        custom_id="approve_btn"
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass  # handled in DiscordService

    @discord.ui.button(
        label="Edit",
        style=discord.ButtonStyle.primary,
        custom_id="edit_btn"
    )
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass  # handled in DiscordService

    @discord.ui.button(
        label="Reject",
        style=discord.ButtonStyle.danger,
        custom_id="reject_btn"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass  # handled in DiscordService