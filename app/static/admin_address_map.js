const STATUS_LABELS = {
  planned: 'Planlagt',
  notscheduled: 'Ikke planlagt',
  informed: 'Beboer/kunde informeret',
  completed: 'Skiftet',
  closed: 'Afsluttet',
  not_home: 'Ikke hjemme',
  needs_reschedule: 'Behov for ny dato',
  unplanned: 'Ikke planlagt',
}

const STATUS_COLORS = {
  planned: '#f59e0b',
  notscheduled: '#94a3b8',
  informed: '#38bdf8',
  completed: '#22c55e',
  closed: '#94a3b8',
  not_home: '#ef4444',
  needs_reschedule: '#f97316',
  unplanned: '#64748b',
}

const SELECTED_COLOR = '#a855f7'

const MAP_DEFAULT = [56.2639, 9.5018]
const MAP_ZOOM = 7
const MAP_CENTER_ZOOM = 13

const searchInput = document.getElementById('map-search')
const statusSelect = document.getElementById('map-status')
const missingList = document.getElementById('missing-list')
const missingCount = document.getElementById('missing-count')
const legend = document.getElementById('map-legend')
const editHint = document.getElementById('edit-hint')
const selectedList = document.getElementById('selected-list')
const selectedCount = document.getElementById('selected-count')
const selectedClear = document.getElementById('selected-clear')
const selectedExport = document.getElementById('selected-export')
const sidebarToggle = document.getElementById('map-sidebar-toggle')
const mapLayout = document.querySelector('.map-layout')
const mapSidebar = document.querySelector('.map-sidebar')

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


const buildLegend = () => {
  legend.innerHTML = ''
  Object.entries(STATUS_COLORS).forEach(([status, color]) => {
    const item = document.createElement('div')
    item.className = 'map-legend-item'
    item.innerHTML = `
      <span class="map-legend-swatch" style="background: ${color}"></span>
      <span>${STATUS_LABELS[status] || status}</span>
    `
    legend.appendChild(item)
  })
  const selectedItem = document.createElement('div')
  selectedItem.className = 'map-legend-item'
  selectedItem.innerHTML = `
    <span class="map-legend-swatch" style="background: ${SELECTED_COLOR}"></span>
    <span>Markeret</span>
  `
  legend.appendChild(selectedItem)
}

const normalizeStatus = (status) => (status || '').trim().toLowerCase()
const statusColor = (status) =>
  STATUS_COLORS[normalizeStatus(status)] || STATUS_COLORS.unplanned

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

const updateMarkers = () => {
  markerLayer.clearLayers()
  addresses
    .filter((row) => row.latitude !== null && row.longitude !== null)
    .forEach((row) => {
      const isSelected = selectedIds.includes(row.id)
      const marker = L.circleMarker([row.latitude, row.longitude], {
        radius: isSelected ? 9 : 7,
        color: isSelected ? SELECTED_COLOR : statusColor(row.status),
        weight: isSelected ? 4 : 2,
        fillColor: statusColor(row.status),
        fillOpacity: 0.8,
      })
      marker.bindPopup(
        `<strong>${row.street} ${row.house_no}</strong><br>${row.zip} ${row.city}<br>${
          STATUS_LABELS[normalizeStatus(row.status)] || row.status
        }<br><div class="map-popup-actions">
          <button type="button" class="ghost-button map-popup-button" data-action="edit-coords" data-address-id="${
            row.id
          }">Rediger koordinat</button>
          <a class="ghost-button map-popup-button" href="/admin/addresses/${row.id}/edit">Åben adresse</a>
          <button type="button" class="ghost-button map-popup-button" data-action="select-status" data-address-id="${
            row.id
          }">${isSelected ? 'Fjern markering' : 'Markér'}</button>
        </div>`
      )
      markerLayer.addLayer(marker)
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
  const missing = addresses.filter(
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
        <button type="button" class="ghost-button" data-action="geocode">Genberegn</button>
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
        <span class="hint">${STATUS_LABELS[normalizeStatus(row.status)] || row.status}</span>
      </div>
      <button type="button" class="ghost-button" data-address-id="${row.id}">Fjern</button>
    `
    item.querySelector('button').addEventListener('click', () => {
      selectedIds = selectedIds.filter((id) => id !== row.id)
      saveSelectedIds()
      updateMarkers()
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
  if (statusSelect.value && statusSelect.value !== 'all') {
    params.set('status', statusSelect.value)
  }
  const response = await fetch(`/admin/addresses/map-data?${params.toString()}`)
  const data = await response.json()
  addresses = data.addresses || []
  updateMarkers()
  renderMissingList()
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
statusSelect.addEventListener('change', loadMapData)
if (selectedClear) {
  selectedClear.addEventListener('click', () => {
    selectedIds = []
    saveSelectedIds()
    updateMarkers()
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

buildLegend()
updateEditHint()
loadSelectedIds()
loadSidebarState()
loadMapData()
