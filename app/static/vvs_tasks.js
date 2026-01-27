document.addEventListener('DOMContentLoaded', () => {
  const triggers = document.querySelectorAll('[data-inline-edit-trigger]')

  const attachCloseHandler = (container) => {
    const closeButton = container.querySelector('[data-inline-edit-close]')
    if (!closeButton) return
    closeButton.addEventListener('click', () => {
      container.classList.add('is-hidden')
    })
  }

  const attachFormHandler = (container) => {
    const form = container.querySelector('[data-inline-edit-form]')
    if (!form) return
    form.addEventListener('submit', async (event) => {
      event.preventDefault()
      const formData = new FormData(form)
      const response = await fetch(form.action, {
        method: 'POST',
        body: formData,
        headers: {
          'X-Requested-With': 'inline'
        }
      })
      const contentType = response.headers.get('content-type') || ''
      if (contentType.includes('application/json')) {
        const payload = await response.json()
        if (payload.success) {
          window.location.reload()
          return
        }
      }
      const html = await response.text()
      container.innerHTML = html
      container.classList.remove('is-hidden')
      attachFormHandler(container)
      attachCloseHandler(container)
    })
  }

  const loadForm = async (appointmentId, container) => {
    const response = await fetch(`/vvs/tasks/${appointmentId}/edit?inline=1`, {
      headers: {
        'X-Requested-With': 'inline'
      }
    })
    const html = await response.text()
    container.innerHTML = html
    container.dataset.loaded = 'true'
    container.classList.remove('is-hidden')
    attachFormHandler(container)
    attachCloseHandler(container)
  }

  triggers.forEach((trigger) => {
    trigger.addEventListener('click', async (event) => {
      event.preventDefault()
      const appointmentId = trigger.getAttribute('data-inline-edit-trigger')
      if (!appointmentId) return
      const container = document.querySelector(`[data-inline-edit="${appointmentId}"]`)
      if (!container) return
      if (container.dataset.loaded === 'true') {
        container.classList.toggle('is-hidden')
        return
      }
      await loadForm(appointmentId, container)
    })
  })
})
