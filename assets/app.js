function mb(value)
{
    return (value / 1024 / 1024).toFixed(2);
}

function gb(value)
{
    return (value / 1024 / 1024 / 1024).toFixed(2);
}

function formatUptime(seconds)
{
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return days + "d " + hours + "h " + mins + "m";
}

let currentFlamegraphUrl = "";

function escapeHtml(value)
{
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function renderMetrics(targetId, pairs)
{
    const html = pairs
        .map((item) => "<div class='metric'><span>" + escapeHtml(item.label) + "</span><strong>" + escapeHtml(item.value) + "</strong></div>")
        .join("");
    document.getElementById(targetId).innerHTML = html;
}

function renderRows(rows)
{
    if (!rows || rows.length === 0)
    {
        return "<p>No rows returned.</p>";
    }

    const columns = Object.keys(rows[0]);
    let html = "<table><thead><tr>";

    for (const col of columns)
    {
        html += "<th>" + escapeHtml(col) + "</th>";
    }

    html += "</tr></thead><tbody>";

    for (const row of rows)
    {
        html += "<tr>";
        for (const col of columns)
        {
            html += "<td>" + escapeHtml(row[col]) + "</td>";
        }
        html += "</tr>";
    }

    html += "</tbody></table>";
    return html;
}

function renderSchema(schema)
{
    if (!schema || !schema.columns)
    {
        return "<p>No schema data.</p>";
    }

    const rows = schema.columns.map((column) => ({
        name: column.name,
        type: column.type,
        primary: column.isPrimaryKey,
        foreignKey: column.foreignKey ? (column.foreignKey.table + "." + column.foreignKey.column) : "-"
    }));

    return "<div class='badge'>" + escapeHtml(schema.tableName) + " | rows: " + escapeHtml(schema.rowCount) + "</div>" + renderRows(rows);
}

function renderResultObject(data)
{
    if (!data)
    {
        return "<p>No result.</p>";
    }

    if (data.result && data.profile)
    {
        let html = "<div class='badge'>Profile: " + escapeHtml(data.profile.profileFile) + " | " + escapeHtml(data.profile.durationMs) + " ms</div>";
        if (data.profile.flamegraph && data.profile.flamegraph.urlPath)
        {
            html += "<div><a href='" + escapeHtml(data.profile.flamegraph.urlPath) + "' target='_blank' rel='noopener noreferrer'>Open Flamegraph</a></div>";
        }
        else if (data.profile.flamegraphError)
        {
            html += "<div class='flamegraphMeta'>Flamegraph error: " + escapeHtml(data.profile.flamegraphError) + "</div>";
        }
        html += renderResultObject(data.result);
        return html;
    }

    if (data.rows)
    {
        return renderRows(data.rows);
    }

    if (data.schema)
    {
        return renderSchema(data.schema);
    }

    if (typeof data.count === "number")
    {
        return "<div class='badge'>Count</div><pre>" + data.count + "</pre>";
    }

    if (data.stats)
    {
        return "<pre>" + escapeHtml(JSON.stringify(data.stats, null, 2)) + "</pre>";
    }

    return "<pre>" + escapeHtml(JSON.stringify(data, null, 2)) + "</pre>";
}

function renderBulkResults(data)
{
    if (!data.results)
    {
        return renderResultObject(data);
    }

    const html = data.results.map((item) =>
    {
        return "<div class='statement'>" +
            "<div class='badge'>Statement " + item.statementNumber + "</div>" +
            "<pre>" + escapeHtml(item.statement) + "</pre>" +
            renderResultObject(item.result) +
            "</div>";
    }).join("");

    return "<div class='resultStack'>" + html + "</div>";
}

function renderProfiles(data)
{
    if (!data.profiles || data.profiles.length === 0)
    {
        document.getElementById("profiles").innerHTML = "<p>No profile files yet.</p>";
        return;
    }

    const html = data.profiles.map((item) =>
    {
        return "<div class='profileItem'>" +
            "<strong>" + escapeHtml(item.profileFile) + "</strong><br>" +
            "Size: " + mb(item.sizeBytes) + " MB<br>" +
            "Created: " + escapeHtml(item.createdAt) + "<br>" +
            "Duration: " + escapeHtml(item.durationMs) + " ms" +
            "</div>";
    }).join("");

    document.getElementById("profiles").innerHTML = html;
}

function renderFlamegraph(data)
{
    const meta = document.getElementById("flamegraphMeta");
    const link = document.getElementById("flamegraphLink");
    if (!data.flamegraphs || data.flamegraphs.length === 0)
    {
        meta.textContent = "No flamegraph generated yet.";
        link.classList.add("hidden");
        link.removeAttribute("href");
        currentFlamegraphUrl = "";
        return;
    }

    const latest = data.flamegraphs[0];
    meta.textContent = "Latest: " + latest.flamegraphFile + " | Created: " + latest.createdAt;
    link.classList.remove("hidden");
    if (latest.urlPath !== currentFlamegraphUrl)
    {
        currentFlamegraphUrl = latest.urlPath;
        link.href = latest.urlPath + "?t=" + Date.now();
    }
}

function renderPiStats(data)
{
    renderMetrics("piStats", [
        { label: "CPU", value: Number(data.cpuPercent).toFixed(1) + "%" },
        { label: "CPU Temp", value: data.cpuTempC == null ? "N/A" : data.cpuTempC + " °C" },
        { label: "RAM", value: gb(data.memoryUsedBytes) + " / " + gb(data.memoryTotalBytes) + " GB (" + data.memoryPercent + "%)" },
        { label: "Disk /", value: gb(data.diskUsedBytes) + " / " + gb(data.diskTotalBytes) + " GB (" + data.diskPercent + "%)" },
        { label: "Load Avg (1m)", value: data.loadAverage.one },
        { label: "Uptime", value: formatUptime(data.uptimeSeconds) }
    ]);
}

async function refreshDashboard()
{
    const [statsRes, memRes, profilesRes, flamegraphsRes] = await Promise.all([
        fetch("/stats"),
        fetch("/memory"),
        fetch("/profiles?limit=8"),
        fetch("/flamegraphs-meta?limit=5")
    ]);

    const stats = await statsRes.json();
    const mem = await memRes.json();
    const profiles = await profilesRes.json();
    const flamegraphs = await flamegraphsRes.json();

    renderMetrics("stats", [
        { label: "Database", value: stats.databaseName },
        { label: "Tables", value: stats.tableCount },
        { label: "Rows", value: stats.totalRows },
        { label: "Queries", value: stats.queryCount },
        { label: "Inserts", value: stats.insertCount },
        { label: "Updates", value: stats.updateCount },
        { label: "Deletes", value: stats.deleteCount }
    ]);

    renderMetrics("memory", [
        { label: "RSS", value: mb(mem.rssBytes) + " MB" },
        { label: "VMS", value: mb(mem.vmsBytes) + " MB" },
        { label: "Python Current", value: mb(mem.pythonCurrentBytes) + " MB" },
        { label: "Python Peak", value: mb(mem.pythonPeakBytes) + " MB" }
    ]);

    renderProfiles(profiles);
    renderFlamegraph(flamegraphs);
}

async function refreshPiStats()
{
    try
    {
        const res = await fetch("/pi-stats");
        const data = await res.json();
        renderPiStats(data);
    }
    catch (err)
    {
        document.getElementById("piStats").innerHTML = "<p>Unable to load Pi stats.</p>";
    }
}

async function runQuery(profile)
{
    const query = document.getElementById("queryBox").value;
    const endpoint = profile ? "/profile/query" : "/query";

    const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query })
    });

    const data = await res.json();
    document.getElementById("results").innerHTML = renderResultObject(data);
    await refreshDashboard();
}

async function runBulkQueries(profile)
{
    const queries = document.getElementById("bulkQueryBox").value;
    const endpoint = profile ? "/profile/bulk-query" : "/bulk-query";

    const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ queries: queries })
    });

    const data = await res.json();
    document.getElementById("results").innerHTML = renderBulkResults(data);
    await refreshDashboard();
}

async function clearProfileFiles()
{
    await fetch("/profiles/clear", { method: "POST" });
    await refreshDashboard();
}

setInterval(refreshDashboard, 2000);
setInterval(refreshPiStats, 10000);

refreshDashboard();
refreshPiStats();
