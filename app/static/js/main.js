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

async function copyTextToClipboard(source) {
  const sourceElement = source instanceof HTMLElement ? source : null;
  const text = typeof source === "string"
    ? source
    : sourceElement && "value" in sourceElement
      ? sourceElement.value
      : sourceElement?.textContent || "";

  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const activeElement = document.activeElement;
  const selection = window.getSelection();
  const selectedRanges = [];
  if (selection) {
    for (let index = 0; index < selection.rangeCount; index += 1) {
      selectedRanges.push(selection.getRangeAt(index).cloneRange());
    }
  }

  const canSelectSource =
    sourceElement instanceof HTMLTextAreaElement ||
    sourceElement instanceof HTMLInputElement;
  const canUseSource =
    canSelectSource &&
    sourceElement.isConnected &&
    sourceElement.getClientRects().length > 0;

  const copyFromElement = (element) => {
    element.focus();
    if ("select" in element) {
      element.select();
    }
    if ("setSelectionRange" in element) {
      element.setSelectionRange(0, text.length);
    }
    return document.execCommand("copy");
  };

  try {
    const copied = canUseSource
      ? copyFromElement(sourceElement)
      : (() => {
          const textarea = document.createElement("textarea");
          textarea.value = text;
          textarea.setAttribute("readonly", "");
          textarea.style.position = "fixed";
          textarea.style.top = "-9999px";
          textarea.style.left = "-9999px";
          document.body.appendChild(textarea);
          textarea.focus();
          textarea.select();
          textarea.setSelectionRange(0, text.length);
          try {
            return document.execCommand("copy");
          } finally {
            textarea.remove();
          }
        })();
    if (!copied) {
      throw new Error("Copy command was rejected");
    }
  } finally {
    if (selection) {
      selection.removeAllRanges();
      selectedRanges.forEach((range) => selection.addRange(range));
    }
    if (activeElement && typeof activeElement.focus === "function") {
      activeElement.focus();
    }
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
