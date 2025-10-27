<script>
document.addEventListener("DOMContentLoaded", () => {
    const afflictionRows = document.getElementById("afflictionRows");
    const addRowButton = document.getElementById("addAfflictionRow");

    // --- Pre-render the severity dropdown via Jinja ---
    const severityDropdown = `
        <select name="severity[]">
            {% for level in AFFLICTION_LEVELS %}
                <option value="{{ level }}">{{ level }}</option>
            {% endfor %}
        </select>
    `;

    // --- Pre-render datalist of known afflictions for autocomplete ---
    const afflictionDatalist = `
        <datalist id="afflictionOptions">
            {% for aff in AFFLICTION_LIST %}
                <option value="{{ aff }}">
            {% endfor %}
        </datalist>
    `;

    // Inject datalist into the page once (below the table)
    afflictionRows.insertAdjacentHTML('afterend', afflictionDatalist);

    // --- Add Row Button logic ---
    addRowButton.addEventListener("click", () => {
        const newRow = document.createElement("tr");
        newRow.innerHTML = `
            <td>
                <input type="text" name="affliction[]" placeholder="Enter condition" list="afflictionOptions">
            </td>
            <td>${severityDropdown}</td>
        `;
        afflictionRows.appendChild(newRow);
    });
});
</script>
