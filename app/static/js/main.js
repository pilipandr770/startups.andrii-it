document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("pitch-chat-form");
    if (!form) return;

    const slug = form.dataset.slug;
    const input = document.getElementById("pitch-chat-input");
    const log = document.getElementById("pitch-chat-log");
    let history = [];

    function appendMessage(role, text) {
        const div = document.createElement("div");
        div.className = "msg " + (role === "user" ? "msg-user" : "msg-bot");
        div.textContent = (role === "user" ? "You: " : "Assistant: ") + text;
        log.appendChild(div);
        log.scrollTop = log.scrollHeight;
    }

    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        const message = input.value.trim();
        if (!message) return;

        appendMessage("user", message);
        input.value = "";

        try {
            const res = await fetch(`/chatbot/${slug}/message`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message, history }),
            });
            const data = await res.json();
            if (data.reply) {
                appendMessage("assistant", data.reply);
                history.push({ role: "user", content: message });
                history.push({ role: "assistant", content: data.reply });
            } else if (data.error) {
                appendMessage("assistant", "Error: " + data.error);
            }
        } catch (err) {
            appendMessage("assistant", "Connection error. Please try again.");
        }
    });
});
