import json
import streamlit as st

from google import genai
from google.genai import types
from twilio.rest import Client as TwilioClient

from prompts import (
    MENU_XRAY_SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
    SUMMARY_REQUEST_PROMPT,
)


# ============================================================
# CONFIG
# ============================================================

MODEL_NAME = "gemini-3.5-flash-lite"

st.set_page_config(
    page_title="MenuXray",
    page_icon="🍽️",
    layout="centered",
)


# ============================================================
# SECRETS
# ============================================================

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_FROM = st.secrets["TWILIO_WHATSAPP_FROM"]
TWILIO_CONTENT_SID = st.secrets["TWILIO_CONTENT_SID"]


# ============================================================
# CLIENTS
# ============================================================

@st.cache_resource
def get_gemini_client():
    return genai.Client(
        api_key=GEMINI_API_KEY
    )


@st.cache_resource
def get_twilio_client():
    return TwilioClient(
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN,
    )


gemini_client = get_gemini_client()
twilio_client = get_twilio_client()


# ============================================================
# MESSAGE FUNCTIONS
# ============================================================

def render_message(message):
    """
    Render a single chat message.
    """

    with st.chat_message(message["role"]):

        if message["kind"] == "text":
            st.write(message["content"])

        elif message["kind"] == "image":
            st.image(message["content"])


def add_message(role, kind, content):
    """
    Add a message to session state and immediately render it.
    """

    st.session_state.messages.append(
        {
            "role": role,
            "kind": kind,
            "content": content,
        }
    )

    render_message(
        st.session_state.messages[-1]
    )


# ============================================================
# GEMINI
# ============================================================

def ask_gemini(parts):
    """
    Send content to the existing Gemini conversation.
    """

    try:

        response = st.session_state.chat.send_message(
            parts
        )

        return response.text

    except Exception as error:

        return (
            "Sorry, something went wrong while "
            f"processing your request:\n\n{error}"
        )


# ============================================================
# WHATSAPP HELPERS
# ============================================================

def clean_whatsapp_number(number):
    """
    Convert the user's phone number into Twilio WhatsApp format.
    """

    number = number.strip()

    # Remove spaces, brackets and hyphens
    number = (
        number
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    # Add whatsapp: prefix if missing
    if not number.startswith("whatsapp:"):
        number = f"whatsapp:{number}"

    return number


def clean_whatsapp_text(text):
    """
    Clean and limit the WhatsApp summary.
    """

    if not text:
        return "No menu summary available."

    # Remove unnecessary newlines
    text = " ".join(text.split())

    # Keep template variable reasonably sized
    if len(text) > 1500:
        text = text[:1500] + "..."

    return text


# ============================================================
# SEND WHATSAPP
# ============================================================

def send_whatsapp(to_number, user_name, summary):
    """
    Send the MenuXray summary to WhatsApp using Twilio.
    """

    try:

        # --------------------------------------------
        # Format recipient
        # --------------------------------------------

        whatsapp_to = clean_whatsapp_number(
            to_number
        )

        # --------------------------------------------
        # Prepare template variables
        #
        # {{1}} = user name
        # {{2}} = menu summary
        # --------------------------------------------

        content_variables = json.dumps(
            {
                "1": user_name,
                "2": clean_whatsapp_text(summary),
            },
            ensure_ascii=False,
        )

        # --------------------------------------------
        # Send WhatsApp template message
        # --------------------------------------------

        message = twilio_client.messages.create(

            from_=TWILIO_WHATSAPP_FROM,

            to=whatsapp_to,

            content_sid=TWILIO_CONTENT_SID,

            content_variables=content_variables,
        )

        return True, message.sid

    except Exception as error:

        return False, str(error)


# ============================================================
# STEP 1: ONBOARDING
# ============================================================

if "onboarded" not in st.session_state:

    st.title("🍽️ MenuXray")

    st.caption(
        "Scan it. Understand it. Compare it. Choose better."
    )

    with st.form("onboarding_form"):

        name = st.text_input(
            "Your name"
        )

        whatsapp_number = st.text_input(
            "WhatsApp number (with country code)",
            placeholder="+91XXXXXXXXXX",
            help=(
                "Enter the WhatsApp number where "
                "MenuXray should send the summary."
            ),
        )

        submitted = st.form_submit_button(
            "Let's go 🚀"
        )

    if submitted:

        if (
            not name.strip()
            or not whatsapp_number.strip()
        ):

            st.warning(
                "Please fill in both your name "
                "and WhatsApp number."
            )

        else:

            st.session_state.name = (
                name.strip()
            )

            st.session_state.whatsapp_number = (
                whatsapp_number.strip()
            )

            # ----------------------------------------
            # Create Gemini conversation
            # ----------------------------------------

            st.session_state.chat = (
                gemini_client.chats.create(
                    model=MODEL_NAME,
                    config=types.GenerateContentConfig(
                        system_instruction=(
                            MENU_XRAY_SYSTEM_PROMPT
                        )
                    ),
                )
            )

            # ----------------------------------------
            # Initialize chat history
            # ----------------------------------------

            st.session_state.messages = []

            st.session_state.onboarded = True

            st.rerun()

    st.stop()


# ============================================================
# STEP 2: CHAT INTERFACE
# ============================================================

header_col, button_col = st.columns(
    [5, 2],
    vertical_alignment="center",
)


with header_col:

    st.title("🍽️ MenuXray")


with button_col:

    # Welcome message = 1 message.
    # Enable WhatsApp after user interacts with menu.
    send_disabled = (
        len(st.session_state.messages) <= 1
    )

    if st.button(
        "📤 Send to WhatsApp",
        disabled=send_disabled,
        use_container_width=True,
    ):

        # --------------------------------------------
        # Generate summary
        # --------------------------------------------

        with st.spinner(
            "Preparing your menu summary..."
        ):

            summary = ask_gemini(
                [SUMMARY_REQUEST_PROMPT]
            )

        # --------------------------------------------
        # Send summary
        # --------------------------------------------

        success, info = send_whatsapp(
            st.session_state.whatsapp_number,
            st.session_state.name,
            summary,
        )

        # --------------------------------------------
        # Result
        # --------------------------------------------

        if success:

            st.success(
                "✅ Menu summary sent to WhatsApp! 📲"
            )

            st.caption(
                f"Message SID: {info}"
            )

        else:

            st.error(
                "❌ WhatsApp message failed."
            )

            st.code(
                info,
                language="text",
            )


# ============================================================
# USER INFORMATION
# ============================================================

st.caption(
    f"Logged in as {st.session_state.name} "
    f"- summaries go to "
    f"{st.session_state.whatsapp_number}"
)


# ============================================================
# CHAT HISTORY
# ============================================================

if not st.session_state.messages:

    add_message(
        "assistant",
        "text",
        WELCOME_MESSAGE_TEMPLATE.format(
            name=st.session_state.name
        ),
    )

else:

    for message in st.session_state.messages:

        render_message(message)


# ============================================================
# USER INPUT
# ============================================================

user_input = st.chat_input(
    "Ask about the menu, or upload a menu photo",
    accept_file=True,
    file_type=[
        "jpg",
        "jpeg",
        "png",
        "webp",
    ],
)


# ============================================================
# PROCESS USER INPUT
# ============================================================

if user_input:

    photo = (
        user_input.files[0]
        if user_input.files
        else None
    )

    text = user_input.text

    parts = []


    # ========================================================
    # IMAGE
    # ========================================================

    if photo is not None:

        photo_bytes = photo.getvalue()

        # Display uploaded image
        add_message(
            "user",
            "image",
            photo_bytes,
        )

        # Send image to Gemini
        parts.append(
            types.Part.from_bytes(
                data=photo_bytes,
                mime_type=photo.type,
            )
        )


    # ========================================================
    # TEXT
    # ========================================================

    if text:

        add_message(
            "user",
            "text",
            text,
        )

        parts.append(text)


    # ========================================================
    # IMAGE ONLY
    # ========================================================

    elif photo is not None:

        parts.append(
            "Analyze this restaurant menu carefully. "
            "Extract the visible dishes, prices, categories, "
            "ingredients, dietary labels, spice information, "
            "and other useful menu information. "
            "Do not invent information that is not visible."
        )


    # ========================================================
    # SEND TO GEMINI
    # ========================================================

    if parts:

        with st.spinner(
            "🔍 Analyzing your menu..."
        ):

            answer = ask_gemini(parts)

        add_message(
            "assistant",
            "text",
            answer,
        )