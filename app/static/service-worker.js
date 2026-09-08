self.addEventListener('push', (event) => {
  const fallback = {
    title: 'Ny beboerbesked',
    body: 'Der er kommet en ny besked',
    url: '/admin/messages?folder=new',
    tag: 'resident-message'
  }
  let payload = fallback
  if (event.data) {
    try {
      payload = { ...fallback, ...event.data.json() }
    } catch (_error) {
      payload = fallback
    }
  }

  event.waitUntil(self.registration.showNotification(payload.title, {
    body: payload.body,
    icon: '/static/icon-192.png',
    badge: '/static/icon-192.png',
    tag: payload.tag,
    data: { url: payload.url }
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const requestedUrl = new URL(
    event.notification.data?.url || '/admin/messages?folder=new',
    self.location.origin
  )
  const targetUrl = requestedUrl.origin === self.location.origin
    ? requestedUrl.href
    : new URL('/admin/messages?folder=new', self.location.origin).href

  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.navigate(targetUrl)
        return client.focus()
      }
    }
    return self.clients.openWindow(targetUrl)
  })())
})
