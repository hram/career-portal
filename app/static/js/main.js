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
