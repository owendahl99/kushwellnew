// simple mobile menu toggle
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("menu-toggle");
  const nav = document.getElementById("nav-links");
  if (toggle && nav) {          
    toggle.addEventListener("click", () => {
      nav.classList.toggle("show");
    });
  }
});
