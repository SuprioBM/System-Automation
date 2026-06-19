import discord
import traceback


class DiscordService:
    def __init__(self, token: str, view_class):

        intents = discord.Intents.all()

        self.client = discord.Client(intents=intents)
        self.token = token
        self.view_class = view_class

        self.pending_messages = []

        # draft_id -> { resume: {...}, linkedin: {...} }
        self.drafts = {}

        # user_id -> edit session
        self.edit_sessions = {}

        # ---------------- SETUP HOOK ----------------
        async def setup_hook():
            print("🔧 Registering persistent view")
            self.client.add_view(self.view_class(draft_id="base"))
            print("✅ Persistent view registered")

        self.client.setup_hook = setup_hook

        # ---------------- READY ----------------
        @self.client.event
        async def on_ready():
            print("===================================")
            print(f"✅ Logged in as {self.client.user}")
            print("===================================")

            for msg in self.pending_messages:
                await self._send(*msg)

            self.pending_messages.clear()

            print("🚀 Bot ready for interactions")

        # ---------------- INTERACTION HANDLER ----------------
        @self.client.event
        async def on_interaction(interaction: discord.Interaction):
            try:
                cid = interaction.data.get("custom_id", "")
                action = cid

                content = interaction.message.content or ""

                # detect type
                if content.startswith("RESUME|"):
                    draft_type = "resume"
                elif content.startswith("LINKEDIN|"):
                    draft_type = "linkedin"
                else:
                    draft_type = "unknown"

                # extract draft_id
                draft_id = content.split("|")[1].split("\n")[0] if "|" in content else "unknown"

                print(f"➡️ Action: {action} | Type: {draft_type} | Draft: {draft_id}")

                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)

                # ---------------- EDIT ----------------
                if action == "edit_btn":
                    print("✏️ EDIT CLICKED")

                    draft_data = self.drafts.get(draft_id, {})
                    session_data = draft_data.get(draft_type, {})

                    self.edit_sessions[interaction.user.id] = {
                        "draft_id": draft_id,
                        "draft_type": draft_type,
                        "content": session_data.get("content"),
                        "analysis": session_data.get("analysis"),
                        "interaction": interaction
                    }

                    await interaction.followup.send(
                        "✏️ Send your update instruction in chat now.",
                        ephemeral=True
                    )
                    return

                # ---------------- APPROVE / REJECT ----------------
                elif action == "approve_btn":
                    print("🔥 APPROVE CLICKED")

                elif action == "reject_btn":
                    print("❌ REJECT CLICKED")

                # ---------------- BACKEND CALL ----------------
                await self.send_to_backend(
                    {
                        "action": action,
                        "draft_id": draft_id
                    },
                    interaction
                )

            except Exception:
                print("❌ INTERACTION ERROR")
                print(traceback.format_exc())

        # ---------------- MESSAGE HANDLER (EDIT FLOW) ----------------
        @self.client.event
        async def on_message(message):
            if message.author.bot:
                return

            user_id = message.author.id

            if user_id not in self.edit_sessions:
                return

            session = self.edit_sessions.pop(user_id)

            print(f"✏️ EDIT RECEIVED for {session['draft_id']}: {message.content}")

            payload = {
                "action": "edit",
                "draft_id": session["draft_id"],
                "draft_type": session["draft_type"],
                "content": session["content"],
                "feedback": message.content
            }

            interaction = session.get("interaction")

            await self.send_to_backend(payload, interaction)

            await message.channel.send(
                f"✅ AI update triggered for `{session['draft_id']}`"
            )

    # ---------------- STORE DRAFTS ----------------
    def send_draft(self,
                   resume_channel,
                   linkedin_channel,
                   linkedin_text,
                   pdf_path,
                   draft_id,
                   analysis_data,
                   resume_bullets):

        print("📦 Creating draft:", draft_id)

        self.drafts[draft_id] = {
            "resume": {
                "content": resume_bullets,
                "analysis": analysis_data
            },
            "linkedin": {
                "content": linkedin_text,
                "analysis": analysis_data
            }
        }

        resume_view = self.view_class(draft_id=draft_id, draft_type="resume")
        linkedin_view = self.view_class(draft_id=draft_id, draft_type="linkedin")

        self.pending_messages.append((
            resume_channel,
            f"RESUME|{draft_id}\n📄 Resume Draft",
            pdf_path,
            resume_view
        ))

        self.pending_messages.append((
            linkedin_channel,
            f"LINKEDIN|{draft_id}\n📝 LinkedIn Draft\n\n{linkedin_text}",
            None,
            linkedin_view
        ))

    # ---------------- BACKEND ----------------
    async def send_to_backend(self, payload: dict, interaction: discord.Interaction = None):
        try:
            import asyncio
            import requests

            print(f"🌐 Backend call: {payload}")

            response = await asyncio.to_thread(
                requests.post,
                "http://localhost:8000/discord/approval",
                json=payload,
                timeout=120
            )

            data = response.json()

            print(f"📨 Backend response received")

            result = data.get("result")

            if interaction and result:
                formatted = self._format_ai_result(result)

                await interaction.followup.send(
                    formatted,
                    ephemeral=True
                )

            return data

        except Exception:
            print("❌ BACKEND ERROR")
            print(traceback.format_exc())

    # ---------------- FORMAT AI RESPONSE ----------------
    def _format_ai_result(self, result: dict) -> str:
        try:
            if not isinstance(result, dict):
                return str(result)

            if "linkedin_post" in result:
                return f"📝 **Updated LinkedIn Post:**\n\n{result['linkedin_post']}"

            if "resume_bullets" in result:
                bullets = "\n".join(f"- {b}" for b in result["resume_bullets"])
                return f"📄 **Updated Resume:**\n\n{bullets}"

            return f"🤖 AI Result:\n\n{result}"

        except Exception:
            return "⚠️ Could not format AI response"

    # ---------------- SEND MESSAGE ----------------
    async def _send(self, channel_id, content, file=None, view=None):
        channel = self.client.get_channel(channel_id)

        if not channel:
            print("❌ Channel not found:", channel_id)
            return

        kwargs = {}

        if file:
            kwargs["file"] = discord.File(file)

        if view:
            kwargs["view"] = view

        await channel.send(content, **kwargs)

    # ---------------- START ----------------
    def start(self):
        print("🚀 Starting bot...")
        self.client.run(self.token)