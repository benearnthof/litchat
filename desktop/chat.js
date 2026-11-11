
const messagesContainer = document.getElementById("messages");
const chatContainer = document.getElementById("chat-container");
const bookInfo = document.getElementById("book-info");

const MAX_MESSAGES = 200;
const EMOTE_SIZE = 28;

// Twitch-style username color palette.
const USER_COLORS = [
    "#FF0000",
    "#0000FF",
    "#008000",
    "#B22222",
    "#FF7F50",
    "#9ACD32",
    "#FF4500",
    "#2E8B57",
    "#DAA520",
    "#D2691E",
    "#5F9EA0",
    "#1E90FF",
    "#FF69B4",
    "#8A2BE2",
    "#00FF7F"
];

// Keep username colors consistent.
const usernameColors = new Map();


function getUsernameColor(username) {
    if (usernameColors.has(username)) {
        return usernameColors.get(username);
    }

    const hash = Array.from(username).reduce(
        (result, character) =>
            (result * 31 + character.charCodeAt(0)) >>> 0,
        0
    );

    const color = USER_COLORS[hash % USER_COLORS.length];

    usernameColors.set(username, color);

    return color;
}


function isNearBottom() {
    const threshold = 60;

    return (
        chatContainer.scrollHeight -
        chatContainer.scrollTop -
        chatContainer.clientHeight
    ) < threshold;
}


function renderContent(content, parent) {
    for (const item of content) {

        if (item.type === "text") {
            parent.appendChild(
                document.createTextNode(item.value)
            );
        }

        else if (item.type === "emote") {
            const img = document.createElement("img");

            img.className = "emote";
            img.alt = item.name;
            img.title = item.name;

            img.width = EMOTE_SIZE;
            img.height = EMOTE_SIZE;

            // Resolve the emote ID to its local GIF.
            // img.src = `../../assets/emotes/${encodeURIComponent(item.id)}.gif`;
            img.src = `../assets/emotes/${encodeURIComponent(item.id)}.gif`;
            img.loading = "lazy";

            // Hide missing or invalid assets.
            img.onerror = () => {
                img.remove();
            };

            parent.appendChild(img);
        }
    }
}


function addChatMessage(message) {
    const shouldScroll = isNearBottom();

    if (message.type === "error") {
        const errorElement = document.createElement("div");

        errorElement.className = "system-message";
        errorElement.textContent = message.text;

        messagesContainer.appendChild(errorElement);
    }

    else {
        const row = document.createElement("div");

        row.className = "chat-message";

        const username = document.createElement("span");

        username.className = "username";
        username.textContent = message.username;

        username.style.color = getUsernameColor(
            message.username
        );

        const content = document.createElement("span");

        content.className = "message-content";

        renderContent(message.content, content);

        row.appendChild(username);
        row.appendChild(document.createTextNode(": "));
        row.appendChild(content);

        messagesContainer.appendChild(row);
    }

    // Keep the DOM bounded.
    while (messagesContainer.children.length > MAX_MESSAGES) {
        messagesContainer.firstElementChild.remove();
    }

    // Only follow new messages if already near the bottom.
    if (shouldScroll) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}


function setBookInfo(book) {
    bookInfo.textContent = `${book.title} — ${book.author}`;
}


// Expose functions for Python's evaluate_js calls.
window.addChatMessage = addChatMessage;
window.setBookInfo = setBookInfo;
