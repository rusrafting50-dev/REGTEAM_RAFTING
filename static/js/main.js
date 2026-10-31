// main.js — общий JS АтлетБазы

// Переключатель субъектов РФ в шапке — кнопка «+ Добавить субъект
// Российской Федерации» показывает/скрывает поле ввода наименования.
document.addEventListener("DOMContentLoaded", () => {
    const toggleButton = document.getElementById("btnToggleAddSubject");
    const formWrap = document.getElementById("formAddSubjectWrap");
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
