export async function api(path, options = {}) {
    const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });

    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
    }

    return response.json();
}

export async function fetchText(path) {
    const response = await fetch(path);
    if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
    }
    return response.text();
}
