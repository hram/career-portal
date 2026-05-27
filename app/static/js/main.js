function flash(message, type = "success") {
  const root = document.getElementById("flash-root");
  if (!root) {
    return;
  }

  const item = document.createElement("div");
  item.className = `flash flash-${type === "error" ? "error" : "success"}`;
  item.textContent = message;
  root.appendChild(item);

  window.setTimeout(() => {
    item.remove();
  }, 3000);
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);

  textarea.focus();
  textarea.select();

  try {
    const copied = document.execCommand("copy");
    if (!copied) {
      throw new Error("Copy command was rejected");
    }
  } finally {
    textarea.remove();
  }
}

async function confirmDelete(url, name) {
  const confirmed = window.confirm(`Удалить "${name}"?`);
  if (!confirmed) {
    return;
  }

  const response = await fetch(url, { method: "DELETE" });
  if (!response.ok) {
    flash("Не удалось удалить запись", "error");
    return;
  }

  window.location.reload();
}

window.flash = flash;
window.copyTextToClipboard = copyTextToClipboard;
window.confirmDelete = confirmDelete;

function getDragAfterElement(container, y, selector) {
  const elements = [...container.querySelectorAll(selector)];

  return elements.reduce(
    (closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;

      if (offset < 0 && offset > closest.offset) {
        return { offset, element: child };
      }

      return closest;
    },
    { offset: Number.NEGATIVE_INFINITY, element: null },
  ).element;
}

window.getDragAfterElement = getDragAfterElement;

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flash").forEach((item) => {
    window.setTimeout(() => {
      item.remove();
    }, 4000);
  });
});
