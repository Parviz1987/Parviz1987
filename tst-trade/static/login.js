/* Login page: show why the last try failed; show the password while typing if asked. */
(function () {
  const err = document.getElementById("err");
  if (location.search.includes("e=blocked")) {
    err.textContent = "Bu ünvandan çox səhv cəhd oldu: təhlükəsizlik üçün 15 dəqiqə gözləyin.";
    err.hidden = false;
  } else if (location.search.includes("e=1")) {
    err.hidden = false;
  }
  document.getElementById("show").onchange = (e) => {
    document.getElementById("pw").type = e.target.checked ? "text" : "password";
  };
})();
