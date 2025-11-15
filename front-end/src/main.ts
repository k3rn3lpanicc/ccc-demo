import './style.css'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

const API_BASE = 'http://127.0.0.1:3001/api'

interface HistoryEntry {
  timestamp: string
  a_ratio: number
  a_funds_ratio: number
  total_votes: number
}

interface Account {
  index: number
  address: string
  balance: number
}

interface ContractStatus {
  address: string
  bettingFinished: boolean
  balance: number
}

let chart: Chart | null = null
let lastHistoryLength = 0

// Load contract status
async function loadContractStatus() {
  try {
    const response = await fetch(`${API_BASE}/contract/status`)
    const data = await response.json()
    
    if (data.success) {
      const status: ContractStatus = data
      document.getElementById('contract-address')!.textContent = 
        status.address.slice(0, 10) + '...' + status.address.slice(-8)
      document.getElementById('contract-balance')!.textContent = 
        `${status.balance.toFixed(4)} ETH`
      document.getElementById('betting-status')!.textContent = 
        status.bettingFinished ? '🔴 Finished' : '🟢 Active'
      
      // Disable voting if finished
      const voteButton = document.getElementById('vote-button') as HTMLButtonElement
      const finishButton = document.getElementById('finish-button') as HTMLButtonElement
      if (status.bettingFinished) {
        voteButton.disabled = true
        voteButton.textContent = 'Betting Closed'
        finishButton.disabled = true
      }
    }
  } catch (error) {
    console.error('Failed to load contract status:', error)
    document.getElementById('contract-address')!.textContent = 'Error loading'
    document.getElementById('contract-balance')!.textContent = 'Error loading'
    document.getElementById('betting-status')!.textContent = 'Error loading'
  }
}

// Load accounts
async function loadAccounts() {
  try {
    const response = await fetch(`${API_BASE}/accounts`)
    const data = await response.json()
    
    if (data.success) {
      const select = document.getElementById('account-select') as HTMLSelectElement
      select.innerHTML = ''
      
      data.accounts.forEach((account: Account) => {
        const option = document.createElement('option')
        option.value = account.index.toString()
        option.textContent = `#${account.index} ${account.address.slice(0, 20)}...${account.address.slice(-20)} (${account.balance.toFixed(2)} ETH)`
        select.appendChild(option)
      })
    }
  } catch (error) {
    console.error('Failed to load accounts:', error)
    const select = document.getElementById('account-select') as HTMLSelectElement
    select.innerHTML = '<option>Error loading accounts</option>'
  }
}

// Load and display chart
async function loadChart() {
  try {
    const response = await fetch(`${API_BASE}/history`)
    const data = await response.json()
    
    if (data.success && data.history.length > 0) {
      const history: HistoryEntry[] = data.history
      
      // Only update if data changed
      if (history.length === lastHistoryLength && chart) {
        return
      }
      
      lastHistoryLength = history.length
      
      // Hide no-data message
      document.getElementById('no-data-message')!.style.display = 'none'
      
      // Prepare chart data
      const labels = history.map(entry => {
        const date = new Date(entry.timestamp)
        return date.toLocaleTimeString()
      })
      
      const aRatios = history.map(entry => entry.a_ratio * 100) // Convert to percentage
      const aFundsRatios = history.map(entry => entry.a_funds_ratio * 100) // Convert to percentage
      const votes = history.map(entry => entry.total_votes)
      
      // Create or update chart
      const canvas = document.getElementById('ratioChart') as HTMLCanvasElement
      const ctx = canvas.getContext('2d')!
      
      if (chart) {
        // Update existing chart data instead of destroying
        chart.data.labels = labels
        chart.data.datasets[0].data = aRatios
        chart.data.datasets[1].data = aFundsRatios
        chart.update('none') // Update without animation
      } else {
        // Create new chart
        chart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [
              {
                label: 'A-Ratio (% of votes)',
                data: aRatios,
                borderColor: '#00d9ff',
                backgroundColor: 'rgba(0, 217, 255, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointRadius: 6,
                pointBackgroundColor: '#00d9ff',
                pointBorderColor: '#000',
                pointBorderWidth: 2,
                pointHoverRadius: 8,
              },
              {
                label: 'A-Funds-Ratio (% of funds)',
                data: aFundsRatios,
                borderColor: '#00ffcc',
                backgroundColor: 'rgba(0, 255, 204, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointRadius: 6,
                pointBackgroundColor: '#00ffcc',
                pointBorderColor: '#000',
                pointBorderWidth: 2,
                pointHoverRadius: 8,
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
              duration: 750
            },
            scales: {
              y: {
                beginAtZero: true,
                max: 100,
                ticks: {
                  color: '#8ab4f8',
                  callback: function(value) {
                    return value + '%'
                  }
                },
                grid: {
                  color: 'rgba(26, 77, 94, 0.3)'
                }
              },
              x: {
                ticks: {
                  color: '#8ab4f8',
                  maxRotation: 45,
                  minRotation: 45
                },
                grid: {
                  color: 'rgba(26, 77, 94, 0.3)'
                }
              }
            },
            plugins: {
              legend: {
                labels: {
                  color: '#00d9ff',
                  font: {
                    family: "'Courier New', monospace",
                    size: 14
                  }
                }
              },
              tooltip: {
                backgroundColor: '#0d1117',
                titleColor: '#00d9ff',
                bodyColor: '#8ab4f8',
                borderColor: '#00d9ff',
                borderWidth: 1,
                callbacks: {
                  label: function(context) {
                    const index = context.dataIndex
                    const datasetLabel = context.dataset.label
                    return `${datasetLabel}: ${context.parsed.y.toFixed(2)}%`
                  },
                  afterLabel: function(context) {
                    const index = context.dataIndex
                    if (context.datasetIndex === 0) {
                      return `Total Votes: ${votes[index]}`
                    }
                    return ''
                  }
                }
              }
            }
          }
        })
      }
    } else {
      // Show no-data message
      document.getElementById('no-data-message')!.style.display = 'block'
    }
  } catch (error) {
    console.error('Failed to load chart data:', error)
  }
}

// Handle vote submission
async function handleVoteSubmit(event: Event) {
  event.preventDefault()
  
  const form = event.target as HTMLFormElement
  const accountIndex = parseInt((document.getElementById('account-select') as HTMLSelectElement).value)
  const betAmount = parseFloat((document.getElementById('bet-amount') as HTMLInputElement).value)
  const betOn = (document.querySelector('input[name="vote-option"]:checked') as HTMLInputElement).value
  
  const submitButton = document.getElementById('vote-button') as HTMLButtonElement
  const resultDiv = document.getElementById('vote-result')!
  
  // Show loading state
  submitButton.disabled = true
  submitButton.textContent = 'Submitting...'
  resultDiv.className = 'vote-result loading show'
  resultDiv.textContent = '⏳ Encrypting and submitting your vote...'
  
  try {
    const response = await fetch(`${API_BASE}/vote`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        accountIndex,
        betAmount,
        betOn
      })
    })
    
    const data = await response.json()
    
    if (data.success) {
      resultDiv.className = 'vote-result success show'
      resultDiv.innerHTML = `
        ✅ Vote submitted successfully!<br>
        <small>Tx: ${data.txHash.slice(0, 20)}...</small><br>
        <small>Block: ${data.blockNumber}</small><br>
        <small>⏳ Waiting for listener to process...</small>
      `
      
      // Reload data after a delay
      setTimeout(() => {
        loadContractStatus()
        loadChart()
      }, 3000)
      
    } else {
      throw new Error(data.detail || 'Unknown error')
    }
  } catch (error) {
    resultDiv.className = 'vote-result error show'
    resultDiv.textContent = `❌ Error: ${(error as Error).message}`
  } finally {
    submitButton.disabled = false
    submitButton.textContent = 'Submit Vote'
  }
}

// Handle finish prediction
async function handleFinishPrediction() {
  const modal = document.getElementById('finish-modal')!
  const resultDiv = document.getElementById('finish-result')!
  const confirmButton = document.getElementById('confirm-finish') as HTMLButtonElement
  const cancelButton = document.getElementById('cancel-finish') as HTMLButtonElement
  const finishButton = document.getElementById('finish-button') as HTMLButtonElement
  
  // Show modal
  modal.classList.add('show')
  
  // Reset result
  resultDiv.className = 'vote-result'
  resultDiv.textContent = ''
  
  // Cancel handler
  const cancelHandler = () => {
    modal.classList.remove('show')
  }
  
  // Confirm handler
  const confirmHandler = async () => {
    const winningOption = (document.querySelector('input[name="winner-option"]:checked') as HTMLInputElement).value
    
    confirmButton.disabled = true
    cancelButton.disabled = true
    resultDiv.className = 'vote-result loading show'
    resultDiv.textContent = '⏳ Step 1/3: Finishing betting...'
    
    try {
      // Step 1: Finish betting
      const finishResponse = await fetch(`${API_BASE}/finish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      
      const finishData = await finishResponse.json()
      if (!finishData.success) {
        throw new Error(finishData.detail || 'Failed to finish betting')
      }
      
      resultDiv.textContent = '⏳ Step 2/3: Calculating payouts...'
      
      // Step 2: Calculate payouts
      const payoutsResponse = await fetch(`${API_BASE}/calculate-payouts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ winningOption })
      })
      
      const payoutsData = await payoutsResponse.json()
      if (!payoutsData.success) {
        throw new Error(payoutsData.detail || 'Failed to calculate payouts')
      }
      
      resultDiv.textContent = '⏳ Step 3/3: Setting payouts in contract...'
      
      // Step 3: Set payouts
      const setPayoutsResponse = await fetch(`${API_BASE}/set-payouts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payouts: payoutsData.payouts })
      })
      
      const setPayoutsData = await setPayoutsResponse.json()
      if (!setPayoutsData.success) {
        throw new Error(setPayoutsData.detail || 'Failed to set payouts')
      }
      
      resultDiv.className = 'vote-result success show'
      resultDiv.innerHTML = `
        ✅ Prediction finished successfully!<br>
        <small>Winning option: ${winningOption}</small><br>
        <small>Winners: ${payoutsData.total_winners}</small><br>
        <small>Total pool: ${payoutsData.total_pool} wei</small><br>
        <small>Winners can now claim their payouts!</small>
      `
      
      // Reload data
      setTimeout(() => {
        modal.classList.remove('show')
        loadContractStatus()
        finishButton.disabled = true
        finishButton.textContent = 'Prediction Finished'
      }, 3000)
      
    } catch (error) {
      resultDiv.className = 'vote-result error show'
      resultDiv.textContent = `❌ Error: ${(error as Error).message}`
      confirmButton.disabled = false
      cancelButton.disabled = false
    }
  }
  
  // Add event listeners
  cancelButton.onclick = cancelHandler
  confirmButton.onclick = confirmHandler
}

// Initialize
async function init() {
  await loadContractStatus()
  await loadAccounts()
  await loadChart()
  
  // Setup form handler
  const form = document.getElementById('vote-form')!
  form.addEventListener('submit', handleVoteSubmit)
  
  // Setup finish button
  const finishButton = document.getElementById('finish-button')!
  finishButton.addEventListener('click', handleFinishPrediction)
  
  // Poll for updates every 5 seconds
  setInterval(() => {
    loadContractStatus()
    loadChart()
  }, 5000)
}

// Start the app
init()
