document.addEventListener("DOMContentLoaded", function () {
    const unitField = document.getElementById("id_unit");
    const unitsPerPackRow = document.getElementById("id_units_per_pack")?.closest(".form-row");
    const packsPerBoxRow = document.getElementById("id_packs_per_box")?.closest(".form-row");

    function toggleFields() {
        const value = unitField.value;

        if (value === "piece") {
            if (unitsPerPackRow) {
                unitsPerPackRow.style.display = "none";
                document.getElementById("id_units_per_pack").value = 1;
            }
            if (packsPerBoxRow) {
                packsPerBoxRow.style.display = "none";
                document.getElementById("id_packs_per_box").value = 1;
            }
        } else if (value === "pack") {
            if (unitsPerPackRow) unitsPerPackRow.style.display = "";
            if (packsPerBoxRow) {
                packsPerBoxRow.style.display = "none";
                document.getElementById("id_packs_per_box").value = 1;
            }
        } else if (value === "box") {
            if (unitsPerPackRow) unitsPerPackRow.style.display = "";
            if (packsPerBoxRow) packsPerBoxRow.style.display = "";
        }
    }

    toggleFields(); // run once on load
    unitField.addEventListener("change", toggleFields);
});
