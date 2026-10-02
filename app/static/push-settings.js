document.addEventListener('DOMContentLoaded', async () => {
  const panel = document.querySelector('[data-push-settings]')
  if (!panel) return

  const activateButton = panel.querySelector('[data-push-activate]')
  const deactivateButton = panel.querySelector('[data-push-deactivate]')
  const status = panel.querySelector('[data-push-status]')
  activateButton.disabled = true
  let registration = null

  const setStatus = (message, active = false) => {
    status.textContent = message
    activateButton.classList.toggle('is-hidden', active)
    deactivateButton.classList.toggle('is-hidden', !active)
  }

  const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true
  if (!window.isSecureContext) {
    setStatus('Notifikationer kræver HTTPS. Åbn MeterReplace via https://.')
    return
  }
  // iPhone exposes the push APIs only when opened as a Home Screen web app.
  if (!isStandalone) {
    setStatus('Åbn MeterReplace i Safari, tryk Del og vælg Føj til hjemmeskærm. Åbn derefter appen fra det nye ikon og aktivér notifikationer her.')
    return
  }
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    setStatus('Denne enhed understøtter ikke Web Push. På iPhone kræves iOS 16.4 eller nyere og en app åbnet fra hjemmeskærmen.')
    return
  }

  try {
    const configResponse = await fetch('/api/push/config')
    if (!configResponse.ok) {
      throw new Error('config_failed')
    }
    const config = await configResponse.json()
    if (!config.configured) {
      setStatus('Web Push er ikke konfigureret på serveren.')
      activateButton.disabled = true
      return
    }

    const applicationServerKey = (() => {
      const padding = '='.repeat((4 - config.publicKey.length % 4) % 4)
      const base64 = (config.publicKey + padding).replace(/-/g, '+').replace(/_/g, '/')
      return Uint8Array.from(window.atob(base64), (character) => character.charCodeAt(0))
    })()

    const blockedMessage = 'Notifikationer er blokeret. Åbn iPhones Indstillinger > Notifikationer > MeterReplace, og tillad notifikationer. Åbn derefter denne side igen.'

    const saveSubscription = async (subscription) => {
      const response = await fetch('/api/push/subscriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content },
        body: JSON.stringify(subscription.toJSON())
      })
      if (!response.ok) {
        throw new Error(response.status === 401 || response.status === 403
          ? 'Log ind som administrator igen, og aktivér notifikationer.'
          : 'Abonnementet kunne ikke gemmes på serveren. Prøv igen eller kontakt administratoren.')
      }
    }

    const removeSubscription = async (subscription) => {
      const response = await fetch('/api/push/subscriptions', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content },
        body: JSON.stringify({ endpoint: subscription.endpoint })
      })
      if (!response.ok) throw new Error('unsubscribe_failed')
      await subscription.unsubscribe()
    }

    const subscriptionUsesKey = (subscription, expectedKey) => {
      const currentKey = subscription.options?.applicationServerKey
      if (!currentKey) return false
      const currentBytes = new Uint8Array(currentKey)
      return currentBytes.length === expectedKey.length && currentBytes.every(
        (value, index) => value === expectedKey[index]
      )
    }

    await navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
    registration = await navigator.serviceWorker.ready
    let existingSubscription = await registration.pushManager.getSubscription()
    let keyWasRotated = false
    if (existingSubscription && !subscriptionUsesKey(existingSubscription, applicationServerKey)) {
      await removeSubscription(existingSubscription)
      existingSubscription = null
      keyWasRotated = true
    }
    if (existingSubscription) {
      await saveSubscription(existingSubscription)
      setStatus('Notifikationer er aktive på denne enhed.', true)
    } else if (Notification.permission === 'denied') {
      setStatus(blockedMessage)
      activateButton.disabled = true
    } else if (keyWasRotated) {
      setStatus('Push-nøglen er ændret. Aktivér notifikationer igen.')
    } else {
      setStatus('Notifikationer er ikke aktive på denne enhed.')
    }

    activateButton.addEventListener('click', async () => {
      activateButton.disabled = true
      let savingSubscription = false
      try {
        const permission = await Notification.requestPermission()
        if (permission !== 'granted') {
          setStatus(permission === 'denied' ? blockedMessage : 'Tilladelse til notifikationer blev ikke givet. Tryk Aktivér for at prøve igen.')
          return
        }
        const subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey
        })
        savingSubscription = true
        await saveSubscription(subscription)
        setStatus('Notifikationer er aktive på denne enhed.', true)
      } catch (error) {
        setStatus(Notification.permission === 'denied' ? blockedMessage
          : savingSubscription ? (error instanceof TypeError
            ? 'Kunne ikke kontakte serveren. Kontrollér internetforbindelsen, og prøv igen.'
            : error.message)
          : 'iPhone kunne ikke oprette push-abonnementet. Kontrollér internetforbindelsen, og prøv igen.')
      } finally {
        activateButton.disabled = Notification.permission === 'denied'
      }
    })

    activateButton.disabled = Notification.permission === 'denied'

    deactivateButton.addEventListener('click', async () => {
      deactivateButton.disabled = true
      try {
      const subscription = await registration.pushManager.getSubscription()
      if (subscription) {
          await removeSubscription(subscription)
      }
        setStatus('Notifikationer er ikke aktive på denne enhed.')
      } catch (_error) {
        setStatus('Notifikationer kunne ikke deaktiveres. Prøv igen.')
      } finally {
        deactivateButton.disabled = false
      }
    })
  } catch (_error) {
    setStatus('Push-konfigurationen kunne ikke indlæses. Prøv igen.')
    activateButton.disabled = true
  }
})
