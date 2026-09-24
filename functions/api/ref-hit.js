export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const ref = (url.searchParams.get('ref') || '').slice(0, 100);
  const site = (url.searchParams.get('site') || 'unknown').slice(0, 40);
  if (/^[A-Za-z0-9_-]+$/.test(ref) && /^[A-Za-z0-9_-]+$/.test(site)) {
    const key = site + ':' + ref;
    const cur = parseInt((await context.env.REFS.get(key)) || '0', 10);
    await context.env.REFS.put(key, String(cur + 1));
  }
  return new Response(null, { status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' } });
}
