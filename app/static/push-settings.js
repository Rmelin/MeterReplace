document.addEventListener('DOMContentLoaded', async () => {
  const panel = document.querySelector('[data-push-settings]')
  if (!panel) return

  const activateButton = panel.querySelector('[data-push-activate]')
  const deactivateButton = panel.querySelector('[data-push-deactivate]')
  const status = panel.querySelector('[data-push-status]')
  let registration = null

  const setStatus = (message, active = false) => {
    status.textContent = message
    activateButton.classList.toggle('is-hidden', active)
    deactivateButton.classList.toggle('is-hidden', !active)
  }

  const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    setStatus('Denne enhed understøtter ikke Web Push.')
    activateButton.disabled = true
    return
  }
  if (!window.isSecureContext) {
    setStatus('Notifikationer kræver HTTPS.')
    activateButton.disabled = true
    return
  }
  if (!isStandalone) {
    setStatus('Åbn MeterReplace fra hjemmeskærmen for at aktivere notifikationer.')
    activateButton.disabled = true
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

    const saveSubscription = async (subscription) => {
      const response = await fetch('/api/push/subscriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription.toJSON())
      })
      if (!response.ok) throw new Error('subscription_failed')
    }

    const removeSubscription = async (subscription) => {
      const response = await fetch('/api/push/subscriptions', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
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
      setStatus('Notifikationer er blokeret i iPhones indstillinger.')
      activateButton.disabled = true
    } else if (keyWasRotated) {
      setStatus('Push-nøglen er ændret. Aktivér notifikationer igen.')
    } else {
      setStatus('Notifikationer er ikke aktive på denne enhed.')
    }

    activateButton.addEventListener('click', async () => {
      activateButton.disabled = true
      try {
        const permission = await Notification.requestPermission()
        if (permission !== 'granted') {
          setStatus('Tilladelse til notifikationer blev ikke givet.')
          return
        }
        const subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey
        })
        await saveSubscription(subscription)
        setStatus('Notifikationer er aktive på denne enhed.', true)
      } catch (_error) {
        setStatus('Notifikationer kunne ikke aktiveres. Prøv igen.')
      } finally {
        activateButton.disabled = Notification.permission === 'denied'
      }
    })

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
