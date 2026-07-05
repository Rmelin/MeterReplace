const cssVar = (name, fallback) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() ||
  fallback

const STATUS_LABELS = {
  planned: 'Planlagt',
  notscheduled: 'Ikke planlagt',
  informed: 'Beboer/kunde informeret',
  completed: 'Skiftet',
  closed: 'Afsluttet',
  not_home: 'Ikke hjemme',
  needs_reschedule: 'Behov for ny dato',
  action_required: 'Kræver handling',
  unplanned: 'Ikke planlagt',
}

const STATUS_COLORS = {
  planned: cssVar('--status-planned', '#2563eb'),
  notscheduled: cssVar('--status-unplanned', '#64748b'),
  informed: cssVar('--status-informed', '#38bdf8'),
  completed: cssVar('--status-completed', '#22c55e'),
  closed: cssVar('--status-closed', '#16a34a'),
  not_home: cssVar('--status-not-home', '#ef4444'),
  needs_reschedule: cssVar('--status-needs-reschedule', '#f97316'),
  action_required: cssVar('--error', '#ef4444'),
  unplanned: cssVar('--status-unplanned', '#64748b'),
}

const SELECTED_COLOR = cssVar('--status-selected', '#a855f7')
const BUFFER_RING_COLOR = '#2563eb'
const BLOCKED_RING_COLOR = cssVar('--error', '#ef4444')

const MAP_DEFAULT = [56.2639, 9.5018]
const MAP_ZOOM = 7
const MAP_CENTER_ZOOM = 13

const searchInput = document.getElementById('map-search')
const statusButtons = Array.from(
  document.querySelectorAll('.map-filter-button')
)
const dateInput = document.getElementById('map-date')
const missingList = document.getElementById('missing-list')
const missingCount = document.getElementById('missing-count')
const actionList = document.getElementById('action-list')
const actionCount = document.getElementById('action-count')
const editHint = document.getElementById('edit-hint')
const selectedList = document.getElementById('selected-list')
const selectedCount = document.getElementById('selected-count')
const selectedClear = document.getElementById('selected-clear')
const selectedExport = document.getElementById('selected-export')
const sidebarToggle = document.getElementById('map-sidebar-toggle')
const mapLayout = document.querySelector('.map-layout')
const mapSidebar = document.querySelector('.map-sidebar')
const dayStatusCards = Array.from(document.querySelectorAll('[data-map-date-card]'))

const map = L.map('address-map').setView(MAP_DEFAULT, MAP_ZOOM)
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 19,
}).addTo(map)

const markerLayer = L.featureGroup().addTo(map)
let currentEditId = null
let addresses = []
let editLabel = ''
let selectedIds = []
let activeStatuses = []
let activeFilter = 'status'
const selectedStorageKey = 'address_map_selected_ids'
const sidebarStorageKey = 'address_map_hide_sidebar'

const updateEditHint = () => {
  if (!editHint) return
  if (currentEditId) {
    editHint.textContent = `Klik på kortet for at gemme koordinater til ${editLabel}.`
  } else {
    editHint.textContent =
      'Vælg en adresse eller klik "Rediger koordinat" på en markør, og klik på kortet for at gemme.'
  }
}


const applyFilterSwatches = () => {
  statusButtons.forEach((button) => {
    const status = button.dataset.status
    const filter = button.dataset.filter
    let color = ''
    if (filter === 'selected') {
      color = SELECTED_COLOR
    } else if (status && status !== 'all') {
      color = STATUS_COLORS[status] || STATUS_COLORS.unplanned
    }
    if (color) {
      button.style.setProperty('--status-color', color)
    }
  })
}

const normalizeStatus = (status) => (status || '').trim().toLowerCase()
const statusColor = (status) =>
  STATUS_COLORS[normalizeStatus(status)] || STATUS_COLORS.unplanned
const escapeHtml = (value) =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')

const addAddressMarkerLayer = (latlng, options, popupContent) => {
  const marker = L.circleMarker(latlng, options)
  marker.bindPopup(popupContent)
  markerLayer.addLayer(marker)
}

const loadSelectedIds = () => {
  try {
    const stored = window.localStorage.getItem(selectedStorageKey)
    if (!stored) return
    const parsed = JSON.parse(stored)
    if (Array.isArray(parsed)) {
      selectedIds = parsed.filter((value) => Number.isFinite(value))
    }
  } catch (error) {
    selectedIds = []
  }
}

const saveSelectedIds = () => {
  window.localStorage.setItem(selectedStorageKey, JSON.stringify(selectedIds))
}

const updateSidebarToggle = (hidden) => {
  if (!sidebarToggle || !mapLayout || !mapSidebar) return
  if (hidden) {
    mapLayout.classList.add('is-sidebar-hidden')
    mapSidebar.classList.add('is-hidden')
    sidebarToggle.textContent = 'Vis sidepanel'
  } else {
    mapLayout.classList.remove('is-sidebar-hidden')
    mapSidebar.classList.remove('is-hidden')
    sidebarToggle.textContent = 'Skjul sidepanel'
  }
  window.requestAnimationFrame(() => {
    map.invalidateSize()
    fitMapToVisible()
  })
}

const loadSidebarState = () => {
  if (!sidebarToggle || !mapLayout || !mapSidebar) return
  const stored = window.localStorage.getItem(sidebarStorageKey)
  const hidden = stored === 'true'
  updateSidebarToggle(hidden)
}

const getVisibleAddresses = () => {
  if (activeFilter === 'selected') {
    return addresses.filter((row) => selectedIds.includes(row.id))
  }
  return addresses
}

const updateFilterButtons = () => {
  statusButtons.forEach((button) => {
    const status = button.dataset.status || ''
    const filter = button.dataset.filter
    let isActive = false

    if (filter === 'selected') {
      isActive = activeFilter === 'selected'
    } else if (status === 'all') {
      isActive = activeFilter === 'status' && activeStatuses.length === 0
    } else {
      isActive = activeFilter === 'status' && activeStatuses.includes(status)
    }

    button.classList.toggle('is-active', isActive)
  })
}

const updateDayStatusCards = (selectedDate) => {
  dayStatusCards.forEach((card) => {
    const isActive = Boolean(selectedDate) && card.dataset.dateValue === selectedDate
    card.classList.toggle('is-selected', isActive)
  })
}

const syncDateQueryInUrl = (selectedDate) => {
  const nextUrl = new URL(window.location.href)
  if (selectedDate) {
    nextUrl.searchParams.set('date_query', selectedDate)
  } else {
    nextUrl.searchParams.delete('date_query')
  }
  window.history.replaceState({}, '', nextUrl)
}

const updateMarkers = () => {
  markerLayer.clearLayers()
  getVisibleAddresses()
    .filter((row) => row.latitude !== null && row.longitude !== null)
    .forEach((row) => {
      const isSelected = selectedIds.includes(row.id)
      const statusLabel =
        row.status_label ||
        STATUS_LABELS[normalizeStatus(row.status)] ||
        row.status
      const appointmentAction = row.appointment_href
        ? `<a class="ghost-button map-popup-button" href="${row.appointment_href}">Åben opgave</a>`
        : ''
      const appointmentDetails = [
        row.appointment_time ? `Tid: ${escapeHtml(row.appointment_time)}` : '',
        row.appointment_contractor ? `VVS: ${escapeHtml(row.appointment_contractor)}` : '',
        row.action_reason ? `Handling: ${escapeHtml(row.action_reason)}` : '',
        row.appointment_note ? `Note: ${escapeHtml(row.appointment_note)}` : '',
      ]
        .filter(Boolean)
        .map((value) => `<span>${value}</span>`)
        .join('')
      const latlng = [row.latitude, row.longitude]
      const popupContent = `<strong>${escapeHtml(row.street)} ${escapeHtml(row.house_no)}</strong><br>${escapeHtml(row.zip)} ${escapeHtml(row.city)}<br>${
        escapeHtml(statusLabel)
      }${appointmentDetails ? `<div class="map-popup-task-meta">${appointmentDetails}</div>` : ''}<div class="map-popup-actions">
          <button type="button" class="map-popup-inline-action" data-action="edit-coords" data-address-id="${
            row.id
          }">Rediger koordinat</button>
          <a class="ghost-button map-popup-button" href="/admin/addresses/${row.id}/edit">Åben adresse</a>
          ${appointmentAction}
          <button type="button" class="ghost-button map-popup-button" data-action="select-status" data-address-id="${
            row.id
          }">${isSelected ? 'Fjern markering' : 'Markér'}</button>
        </div>`
      const ringLayers = []
      let outerRadius = 7

      if (row.has_buffer) {
        outerRadius += 4
        ringLayers.push({ radius: outerRadius, color: BUFFER_RING_COLOR, weight: 2 })
      }
      if (row.has_blocked) {
        outerRadius += 3
        ringLayers.push({ radius: outerRadius, color: BLOCKED_RING_COLOR, weight: 2 })
      }
      if (isSelected) {
        ringLayers.push({ radius: outerRadius + 3, color: SELECTED_COLOR, weight: 3 })
      }

      ringLayers
        .slice()
        .reverse()
        .forEach((layer) => {
          addAddressMarkerLayer(
            latlng,
            {
              radius: layer.radius,
              color: layer.color,
              weight: layer.weight,
              fill: false,
              opacity: 1,
            },
            popupContent
          )
        })

      addAddressMarkerLayer(
        latlng,
        {
          radius: 7,
          color: statusColor(row.status),
          weight: 2,
          fillColor: statusColor(row.status),
          fillOpacity: 0.8,
        },
        popupContent
      )
  })
}

const renderActionList = () => {
  if (!actionList || !actionCount) return
  actionList.innerHTML = ''
  const actionRows = getVisibleAddresses().filter((row) => row.action_required)
  actionCount.textContent = String(actionRows.length)
  actionRows.forEach((row) => {
    const item = document.createElement('li')
    item.className = 'map-list-item map-action-item'
    item.dataset.addressId = row.id
    const statusLabel =
      row.action_reason ||
      row.status_label ||
      STATUS_LABELS[normalizeStatus(row.status)] ||
      row.status
    item.innerHTML = `
      <div class="map-list-main">
        <span>${escapeHtml(row.street)} ${escapeHtml(row.house_no)}</span>
        <span class="hint">${escapeHtml(statusLabel)}</span>
        ${
          row.appointment_time
            ? `<span class="hint">${escapeHtml(row.appointment_time)}</span>`
            : ''
        }
      </div>
      <div class="map-list-actions">
        ${
          row.appointment_href
            ? `<a class="ghost-button" href="${row.appointment_href}">Opgave</a>`
            : ''
        }
        <a class="ghost-button" href="/admin/addresses/${row.id}/edit">Adresse</a>
      </div>
    `
    actionList.appendChild(item)
  })
}

const fitMapToVisible = () => {
  const bounds = markerLayer.getBounds()
  if (bounds && bounds.isValid()) {
    map.invalidateSize()
    window.requestAnimationFrame(() => {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 })
    })
    return
  }
  loadMapCenter()
}

const renderMissingList = () => {
  missingList.innerHTML = ''
  const missing = getVisibleAddresses().filter(
    (row) => row.latitude === null || row.longitude === null
  )
  missingCount.textContent = String(missing.length)
  missing.forEach((row) => {
    const item = document.createElement('li')
    item.className = 'map-list-item'
    item.dataset.addressId = row.id
    item.innerHTML = `
      <div class="map-list-main">
        <span>${row.street} ${row.house_no}</span>
        <span class="hint">${row.zip} ${row.city}</span>
      </div>
      <div class="map-list-actions">
        <button type="button" class="ghost-button" data-action="select">Sæt koordinat</button>
        <button type="button" class="ghost-button" data-action="geocode">Søg koordinat</button>
      </div>
    `
    item.addEventListener('click', async (event) => {
      const target = event.target
      if (target instanceof HTMLElement && target.dataset.action === 'geocode') {
        event.stopPropagation()
        try {
          const response = await fetch(`/admin/addresses/${row.id}/geocode`, {
            method: 'POST',
          })
          const result = await response.json()
          if (!response.ok || !result.success) {
            throw new Error('Kunne ikke geokode')
          }
          addresses = addresses.map((entry) =>
            entry.id === row.id
              ? {
                  ...entry,
                  latitude: result.latitude,
                  longitude: result.longitude,
                }
              : entry
          )
          updateMarkers()
          renderMissingList()
        } catch (error) {
          window.alert('Kunne ikke genberegne koordinater. Prøv igen.')
        }
        return
      }

      currentEditId = row.id
      editLabel = `${row.street} ${row.house_no}`
      updateEditHint()
      document
        .querySelectorAll('.map-list-item.is-active')
        .forEach((node) => node.classList.remove('is-active'))
      item.classList.add('is-active')
    })
    missingList.appendChild(item)
  })
}

const renderSelectedList = () => {
  if (!selectedList || !selectedCount) return
  selectedList.innerHTML = ''
  const selected = addresses.filter((row) => selectedIds.includes(row.id))
  selectedCount.textContent = String(selected.length)
  selected.forEach((row) => {
    const item = document.createElement('li')
    item.className = 'map-list-item'
    item.innerHTML = `
      <div class="map-list-main">
        <span>${row.street} ${row.house_no}</span>
        <span class="hint">${
          row.status_label ||
          STATUS_LABELS[normalizeStatus(row.status)] ||
          row.status
        }</span>
      </div>
      <button type="button" class="ghost-button" data-address-id="${row.id}">Fjern</button>
    `
    item.querySelector('button').addEventListener('click', () => {
      selectedIds = selectedIds.filter((id) => id !== row.id)
      saveSelectedIds()
      updateMarkers()
      renderActionList()
      renderSelectedList()
    })
    selectedList.appendChild(item)
  })
}

const loadMapData = async () => {
  const params = new URLSearchParams()
  if (searchInput.value.trim()) {
    params.set('q', searchInput.value.trim())
  }
  if (activeFilter !== 'selected') {
    activeStatuses.forEach((status) => params.append('status', status))
  }
  if (dateInput && dateInput.value) {
    params.set('date', dateInput.value)
  }
  const response = await fetch(`/admin/addresses/map-data?${params.toString()}`)
  const data = await response.json()
  addresses = data.addresses || []
  updateMarkers()
  renderMissingList()
  renderActionList()
  renderSelectedList()
  fitMapToVisible()
}

const saveCoordinates = async (addressId, latitude, longitude) => {
  const response = await fetch(`/admin/addresses/${addressId}/coordinates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ latitude, longitude }),
  })
  if (!response.ok) {
    throw new Error('Kunne ikke gemme koordinater')
  }
}

map.getContainer().addEventListener('click', (event) => {
  const target = event.target
  if (!(target instanceof HTMLElement)) return
  if (target.dataset.action === 'edit-coords') {
    event.preventDefault()
    event.stopPropagation()
    const addressId = Number(target.dataset.addressId)
    if (Number.isNaN(addressId)) return
    const selected = addresses.find((row) => row.id === addressId)
    if (!selected) return
    currentEditId = addressId
    editLabel = `${selected.street} ${selected.house_no}`
    updateEditHint()
    return
  }
  if (target.dataset.action === 'select-status') {
    event.preventDefault()
    event.stopPropagation()
    const addressId = Number(target.dataset.addressId)
    if (Number.isNaN(addressId)) return
    if (selectedIds.includes(addressId)) {
      selectedIds = selectedIds.filter((id) => id !== addressId)
    } else {
      selectedIds = [...selectedIds, addressId]
    }
    saveSelectedIds()
    updateMarkers()
    renderSelectedList()
  }
})

map.on('click', async (event) => {
  if (!currentEditId) return
  const { lat, lng } = event.latlng
  try {
    await saveCoordinates(currentEditId, lat, lng)
    addresses = addresses.map((row) =>
      row.id === currentEditId
        ? { ...row, latitude: lat, longitude: lng }
        : row
    )
    currentEditId = null
    editLabel = ''
    updateEditHint()
    updateMarkers()
    renderMissingList()
  } catch (error) {
    window.alert('Kunne ikke gemme koordinater. Prøv igen.')
  }
})

let searchTimer = null
const triggerSearch = () => {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(loadMapData, 300)
}

searchInput.addEventListener('input', triggerSearch)
if (dateInput) {
  dateInput.addEventListener('change', () => {
    const selectedDate = dateInput.value || ''
    syncDateQueryInUrl(selectedDate)
    updateDayStatusCards(selectedDate)
    loadMapData()
  })
}
statusButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const status = button.dataset.status
    const filter = button.dataset.filter
    if (filter === 'selected') {
      activeFilter = 'selected'
      updateFilterButtons()
      loadMapData()
      return
    }

    activeFilter = 'status'
    if (!status || status === 'all') {
      activeStatuses = []
    } else {
      activeStatuses = activeStatuses.includes(status)
        ? activeStatuses.filter((value) => value !== status)
        : [...activeStatuses, status]
    }

    updateFilterButtons()
    loadMapData()
  })
})
if (selectedClear) {
  selectedClear.addEventListener('click', () => {
    selectedIds = []
    saveSelectedIds()
    updateMarkers()
    renderActionList()
    renderSelectedList()
  })
}

if (selectedExport) {
  selectedExport.addEventListener('click', async () => {
    const selected = addresses.filter((row) => selectedIds.includes(row.id))
    const rows = [
      ['street', 'house_no', 'status'],
      ...selected.map((row) => [row.street, row.house_no, row.status]),
    ]
    const csv = rows.map((row) => row.join(',')).join('\n')
    try {
      await navigator.clipboard.writeText(csv)
      window.alert('CSV kopieret til clipboard')
    } catch (error) {
      window.alert('Kunne ikke kopiere CSV. Prøv igen.')
    }
  })
}

if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    const isHidden = mapSidebar?.classList.contains('is-hidden')
    const next = !isHidden
    window.localStorage.setItem(sidebarStorageKey, String(next))
    updateSidebarToggle(next)
  })
}

const loadMapCenter = async () => {
  try {
    const response = await fetch('/admin/addresses/map-center')
    const data = await response.json()
    if (response.ok && data.success) {
      map.setView([data.latitude, data.longitude], MAP_CENTER_ZOOM)
    }
  } catch (error) {
    return
  }
}

applyFilterSwatches()
updateFilterButtons()
updateDayStatusCards(dateInput?.value || '')
updateEditHint()
loadSelectedIds()
loadSidebarState()
loadMapData()
