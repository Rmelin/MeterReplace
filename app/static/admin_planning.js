document.addEventListener('DOMContentLoaded', () => {
  const panels = document.querySelectorAll('[data-panel]')
  const buttons = document.querySelectorAll('[data-toggle-panel]')
  const orderList = document.querySelector('[data-order-list]')
  const orderInput = document.querySelector('[data-address-order]')
  const plannedTable = document.querySelector('[data-planned-table]')
  const addressFilter = document.querySelector('[data-address-filter]')

  const hidePanel = (panel) => {
    panel.classList.add('is-hidden')
  }

  const showPanel = (panel) => {
    panel.classList.remove('is-hidden')
  }

  const togglePanel = (target) => {
    panels.forEach((panel) => {
      if (panel.getAttribute('data-panel') === target) {
        const isHidden = panel.classList.contains('is-hidden')
        if (isHidden) {
          showPanel(panel)
        } else {
          hidePanel(panel)
        }
      }
    })
  }

  const updatePlannedTable = () => {
    if (!plannedTable || !orderList) return
    const rows = Array.from(plannedTable.querySelectorAll('[data-plan-row]'))
    if (rows.length === 0) return
    const items = Array.from(orderList.querySelectorAll('[data-address-id]'))
    const plannedIds = items.slice(0, rows.length).map((item) => item.dataset.addressId)
    const rowMap = new Map(rows.map((row) => [row.dataset.addressId, row]))
    const tbody = plannedTable.querySelector('tbody')
    plannedIds.forEach((addressId) => {
      const row = rowMap.get(addressId)
      const item = items.find((entry) => entry.dataset.addressId === addressId)
      if (row && tbody) {
        tbody.appendChild(row)
        const cell = row.querySelector('[data-plan-address]')
        if (cell && item) {
          cell.textContent = item.getAttribute('data-address-label') || item.textContent
        }
      }
    })
  }

  const updateOrderListFromPlanned = () => {
    if (!plannedTable || !orderList) return
    const rows = Array.from(plannedTable.querySelectorAll('[data-plan-row]'))
    if (rows.length === 0) return
    const plannedIds = rows.map((row) => row.dataset.addressId).filter(Boolean)
    const remainingIds = Array.from(orderList.querySelectorAll('[data-address-id]'))
      .map((item) => item.dataset.addressId)
      .filter((id) => id && !plannedIds.includes(id))
    const newOrder = [...plannedIds, ...remainingIds]
    newOrder.forEach((addressId) => {
      const item = orderList.querySelector(`[data-address-id="${addressId}"]`)
      if (item) {
        orderList.appendChild(item)
      }
    })
  }

  const updateOrderInput = () => {
    if (!orderList || !orderInput) return
    const ids = Array.from(orderList.querySelectorAll('[data-address-id]'))
      .map((item) => item.getAttribute('data-address-id'))
      .filter(Boolean)
    orderInput.value = ids.join(',')
  }

  const setupOrderListDrag = () => {
    if (!orderList) return
    let draggedItem = null

    orderList.querySelectorAll('li[draggable="true"]').forEach((item) => {
      item.addEventListener('dragstart', (event) => {
        draggedItem = item
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData('text/plain', item.dataset.addressId || '')
        item.classList.add('is-dragging')
      })
      item.addEventListener('dragend', () => {
        item.classList.remove('is-dragging')
        draggedItem = null
        updateOrderInput()
        updatePlannedTable()
      })
    })

    orderList.addEventListener('dragover', (event) => {
      event.preventDefault()
      if (!draggedItem) return
      const target = event.target.closest('li')
      if (!target || target === draggedItem) return
      const rect = target.getBoundingClientRect()
      const shouldInsertBefore = event.clientY < rect.top + rect.height / 2
      orderList.insertBefore(draggedItem, shouldInsertBefore ? target : target.nextSibling)
    })
  }

  const setupPlannedDrag = () => {
    if (!plannedTable) return
    const tbody = plannedTable.querySelector('tbody')
    if (!tbody) return
    let draggedRow = null

    tbody.querySelectorAll('[data-plan-row][draggable="true"]').forEach((row) => {
      row.addEventListener('dragstart', (event) => {
        draggedRow = row
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData('text/plain', row.dataset.addressId || '')
        row.classList.add('is-dragging')
      })
      row.addEventListener('dragend', () => {
        row.classList.remove('is-dragging')
        draggedRow = null
        updateOrderListFromPlanned()
        updateOrderInput()
      })
    })

    tbody.addEventListener('dragover', (event) => {
      event.preventDefault()
      if (!draggedRow) return
      const target = event.target.closest('[data-plan-row]')
      if (!target || target === draggedRow) return
      const rect = target.getBoundingClientRect()
      const shouldInsertBefore = event.clientY < rect.top + rect.height / 2
      tbody.insertBefore(draggedRow, shouldInsertBefore ? target : target.nextSibling)
    })
  }

  const applyFilter = () => {
    if (!addressFilter) return
    const query = addressFilter.value.trim().toLowerCase()
    const items = document.querySelectorAll('[data-address-search]')
    items.forEach((item) => {
      const haystack = (item.getAttribute('data-address-search') || '').toLowerCase()
      const matches = !query || haystack.includes(query)
      if (item.tagName === 'TR') {
        item.style.display = matches ? '' : 'none'
      } else {
        item.style.display = matches ? '' : 'none'
      }
    })
  }

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      const target = button.getAttribute('data-toggle-panel')
      if (!target) return
      togglePanel(target)
    })
  })

  if (addressFilter) {
    addressFilter.addEventListener('input', applyFilter)
  }

  updateOrderInput()
  updatePlannedTable()
  setupOrderListDrag()
  setupPlannedDrag()
})
