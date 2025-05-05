export async function secureFetch(
  input: RequestInfo,
  init?: RequestInit,
  timeout: number = 5000
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  
  try {
    const res = await fetch(input, {
      ...init,
      credentials: "include", // super important for cookies
    });

    return res; // always return the raw response object
  } catch (error) {
    console.error("secureFetch error:", error);

    // Return a fake response with ok=false so frontend doesn’t crash
    return new Response(null, { status: 500, statusText: "Network Error" });
  } finally {
    clearTimeout(id);
  }
}