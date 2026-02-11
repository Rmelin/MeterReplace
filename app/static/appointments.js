document.addEventListener('DOMContentLoaded', () => {
  const triggers = document.querySelectorAll('[data-inline-edit-trigger]')

  const toMinutes = (value) => {
    if (!value) return null
    const parts = value.split(':')
    if (parts.length !== 2) return null
    const hours = Number.parseInt(parts[0], 10)
    const minutes = Number.parseInt(parts[1], 10)
    if (Number.isNaN(hours) || Number.isNaN(minutes)) return null
    return hours * 60 + minutes
  }

  const toTime = (totalMinutes) => {
    const minutes = totalMinutes % (24 * 60)
    const hours = Math.floor(minutes / 60)
    const mins = minutes % 60
    return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`
  }

  const attachDurationSync = (root) => {
    const forms = root.querySelectorAll('[data-duration-form]')
    forms.forEach((form) => {
      if (form.dataset.durationBound === 'true') return
      const startInput = form.querySelector('[data-duration-start]')
      const endInput = form.querySelector('[data-duration-end]')
      const durationInput = form.querySelector('[data-duration-minutes]')
      if (!startInput || !endInput || !durationInput) return

      let updating = false

      const updateEnd = () => {
        if (updating) return
        const startMinutes = toMinutes(startInput.value)
        const duration = Number.parseInt(durationInput.value, 10)
        if (startMinutes === null || Number.isNaN(duration)) return
        updating = true
        endInput.value = toTime(startMinutes + duration)
        updating = false
      }

      const updateDuration = () => {
        if (updating) return
        const startMinutes = toMinutes(startInput.value)
        const endMinutes = toMinutes(endInput.value)
        if (startMinutes === null || endMinutes === null) return
        const duration = endMinutes - startMinutes
        if (duration <= 0) return
        updating = true
        durationInput.value = duration
        updating = false
      }

      startInput.addEventListener('change', updateEnd)
      durationInput.addEventListener('input', updateEnd)
      endInput.addEventListener('change', updateDuration)
      updateDuration()
      form.dataset.durationBound = 'true'
    })
  }

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
      attachDurationSync(container)
    })
  }

  const loadForm = async (appointmentId, container) => {
    const response = await fetch(`/admin/appointments/${appointmentId}/edit?inline=1`, {
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
    attachDurationSync(container)
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

  attachDurationSync(document)
})
