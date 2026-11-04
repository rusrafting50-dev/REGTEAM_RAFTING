// main.js — общий JS АтлетБазы

// Переключатели субъектов РФ и организаций в шапке — кнопка «+ Добавить
// ...» показывает/скрывает поле ввода наименования.
document.addEventListener("DOMContentLoaded", () => {
    const toggles = [
        ["btnToggleAddSubject", "formAddSubjectWrap"],
        ["btnToggleAddOrganization", "formAddOrganizationWrap"],
    ];
    toggles.forEach(([buttonId, wrapId]) => {
        const toggleButton = document.getElementById(buttonId);
        const formWrap = document.getElementById(wrapId);
        if (toggleButton && formWrap) {
            toggleButton.addEventListener("click", () => {
                const isHidden = formWrap.style.display === "none";
                formWrap.style.display = isHidden ? "block" : "none";
                if (isHidden) {
                    const input = formWrap.querySelector("input[name='name']");
                    if (input) input.focus();
                }
            });
        }
    });
});
