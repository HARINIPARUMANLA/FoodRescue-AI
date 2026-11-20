const chatForm = document.getElementById('chatForm');
const userMessage = document.getElementById('userMessage');
const chatMessages = document.getElementById('chatMessages');

function addMessage(text, role) {
  const message = document.createElement('div');
  message.className = `message ${role}`;
  message.textContent = text;
  chatMessages.appendChild(message);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return message;
}

chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = userMessage.value.trim();
  if (!message) return;
  addMessage(message, 'user');
  userMessage.value = '';
  const waiting = addMessage('RescueBot is thinking...', 'bot');
  const sendButton = chatForm.querySelector('button');
  sendButton.disabled = true;
  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    });
    const data = await response.json();
    waiting.textContent = data.reply || 'Sorry, I could not prepare a reply.';
  } catch (error) {
    waiting.textContent = 'Unable to reach the server. Please check that Flask is running.';
  } finally {
    sendButton.disabled = false;
    userMessage.focus();
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
});
