export function toast(message: string, duration = 3000) {
  const toastEl = document.getElementById("toast");
  const toastText = document.getElementById("toastText");
  if (!toastEl || !toastText) return;
  toastText.textContent = message;
  toastEl.style.display = "flex";
  setTimeout(() => {
    toastEl.style.display = "none";
  }, duration);
}
