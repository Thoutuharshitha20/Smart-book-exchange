// Small client-side helper: prevent accidental double submission of forms.
document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", () => {
    const button = form.querySelector('button[type="submit"], button:not([type])');
    if (button && !button.dataset.noDisable) {
      button.dataset.originalText = button.textContent;
      button.disabled = true;
      button.textContent = "Please wait...";
    }
  });
});
