(() => {
    "use strict";

    const container = document.getElementById("dashboard-container");
    const status = document.getElementById("dashboard-status");
    const picker = document.getElementById("dashboard-picker");
    const selector = document.getElementById("dashboard-select");
    const csrfToken = document.querySelector(
        'input[name="csrfmiddlewaretoken"]'
    ).value;

    async function requestEmbed() {
        const response = await fetch(container.dataset.embedEndpoint, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken },
            credentials: "same-origin",
            cache: "no-store",
        });

        if (response.status === 401) {
            throw new Error("Сессия завершилась. Войдите снова.");
        }
        if (response.status === 403) {
            throw new Error("Доступ к телеметрии закрыт.");
        }
        if (!response.ok) {
            throw new Error("Не удалось получить данные для дашборда.");
        }

        const data = await response.json();
        if (
            !data.superset_url ||
            !Array.isArray(data.dashboards) ||
            data.dashboards.length === 0 ||
            !data.guest_token
        ) {
            throw new Error("Сервис вернул неполные данные дашборда.");
        }
        return data;
    }

    function showError(error) {
        status.textContent = error.message || "Не удалось загрузить дашборд.";
        container.replaceChildren();
    }

    async function start() {
        if (!globalThis.supersetEmbeddedSdk?.embedDashboard) {
            throw new Error("Не удалось загрузить библиотеку дашборда.");
        }

        let initialData = await requestEmbed();
        const requestedCode = new URLSearchParams(location.search).get("dashboard");
        const selectedDashboard = initialData.dashboards.find(
            (dashboard) => dashboard.code === requestedCode
        ) || initialData.dashboards[0];
        const supersetUrl = initialData.superset_url;

        selector.replaceChildren();
        for (const dashboard of initialData.dashboards) {
            const option = document.createElement("option");
            option.value = dashboard.code;
            option.textContent = dashboard.title;
            selector.append(option);
        }
        selector.value = selectedDashboard.code;
        picker.hidden = initialData.dashboards.length < 2;
        selector.addEventListener("change", () => {
            const address = new URL(location.href);
            address.searchParams.set("dashboard", selector.value);
            location.assign(address.href);
        });

        async function fetchGuestToken() {
            try {
                const data = initialData || await requestEmbed();
                initialData = null;
                const stillAllowed = data.dashboards.some(
                    (dashboard) =>
                        dashboard.code === selectedDashboard.code &&
                        dashboard.embedded_id === selectedDashboard.embedded_id
                );
                if (!stillAllowed || data.superset_url !== supersetUrl) {
                    throw new Error("Доступ к дашборду изменился. Обновите страницу.");
                }
                return data.guest_token;
            } catch (error) {
                showError(error);
                throw error;
            }
        }

        await globalThis.supersetEmbeddedSdk.embedDashboard({
            id: selectedDashboard.embedded_id,
            supersetDomain: supersetUrl,
            mountPoint: container,
            fetchGuestToken,
            iframeTitle: selectedDashboard.title,
            referrerPolicy: "strict-origin-when-cross-origin",
        });
        status.textContent = "";
    }

    start().catch(showError);
})();
