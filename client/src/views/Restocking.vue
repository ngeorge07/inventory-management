<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>

      <div v-if="successMessage" class="success-message">
        {{ successMessage }}
      </div>

      <!-- Budget slider card -->
      <div class="card budget-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
        </div>
        <div class="budget-controls">
          <div class="slider-row">
            <input
              type="range"
              min="0"
              max="500000"
              step="5000"
              v-model.number="budget"
              class="budget-slider"
            />
            <span class="budget-value">{{ formatCurrency(budget) }}</span>
          </div>

          <div class="usage-bar-section">
            <div class="usage-label">
              {{ t('restocking.budgetUsed') }}:
              <strong>{{ formatCurrency(totalCost) }}</strong>
              / {{ formatCurrency(budget) }}
            </div>
            <div class="usage-track">
              <div
                class="usage-fill"
                :class="{ 'over-budget': overBudget }"
                :style="{ width: Math.min(100, budget > 0 ? (totalCost / budget) * 100 : 0) + '%' }"
              ></div>
            </div>
            <div v-if="overBudget" class="over-budget-warning">
              {{ t('restocking.overBudget') }}
            </div>
          </div>
        </div>
      </div>

      <!-- Recommended items card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommended') }}</h3>
          <span class="total-cost-label">
            {{ t('restocking.totalCost') }}: <strong>{{ formatCurrency(totalCost) }}</strong>
          </span>
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noItems') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.name') }}</th>
                <th>{{ t('restocking.table.gap') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
                <th>{{ t('restocking.table.include') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in recommendations"
                :key="item.item_sku"
                :class="{ 'row-excluded': !item.included }"
              >
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ item.item_name }}</td>
                <td>{{ item.gap }}</td>
                <td>{{ formatCurrency(item.unit_cost) }}</td>
                <td>
                  <input
                    type="number"
                    min="0"
                    v-model.number="quantities[item.item_sku]"
                    class="qty-input"
                  />
                </td>
                <td>{{ formatCurrency(item.lineCost) }}</td>
                <td>{{ t('orders.leadTimeDays', { days: item.lead_time_days }) }}</td>
                <td>
                  <span v-if="item.included" class="badge info">{{ t('restocking.table.include') }}</span>
                  <span v-else class="badge">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="order-footer">
          <button
            class="place-order-btn"
            :disabled="includedItems.length === 0 || overBudget"
            @click="placeOrder"
          >
            {{ t('restocking.placeOrder') }}
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script>
// NOTE: This view intentionally ignores the global FilterBar.
// Demand forecast SKUs don't map to warehouses or categories,
// so warehouse/category/period filters are not applied here.
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency as formatCurrencyUtil } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const formatCurrency = (value) => formatCurrencyUtil(value, currentCurrency.value)

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(100000)
    const quantities = reactive({})
    const successMessage = ref(null)

    const recommendations = computed(() => {
      const mapped = forecasts.value.map(f => {
        const gap = f.forecasted_demand - f.current_demand
        const qty = quantities[f.item_sku] ?? 0
        const lineCost = qty * f.unit_cost
        return { ...f, gap, qty, lineCost }
      })

      // Sort by gap descending
      mapped.sort((a, b) => b.gap - a.gap)

      // Greedy fit: walk sorted list, mark included if fits in remaining budget
      let runningTotal = 0
      return mapped.map(item => {
        if (item.qty > 0 && runningTotal + item.lineCost <= budget.value) {
          runningTotal += item.lineCost
          return { ...item, included: true }
        }
        return { ...item, included: false }
      })
    })

    const includedItems = computed(() => recommendations.value.filter(r => r.included))

    const totalCost = computed(() => includedItems.value.reduce((sum, r) => sum + r.lineCost, 0))

    const overBudget = computed(() => totalCost.value > budget.value)

    const loadForecasts = async () => {
      loading.value = true
      error.value = null
      try {
        const data = await api.getDemandForecasts()
        forecasts.value = data
        // Initialize quantities to max(gap, 1) for each forecast
        data.forEach(f => {
          const gap = f.forecasted_demand - f.current_demand
          quantities[f.item_sku] = Math.max(gap, 1)
        })
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
        console.error(err)
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      try {
        const payload = {
          items: includedItems.value.map(i => ({
            item_sku: i.item_sku,
            item_name: i.item_name,
            quantity: i.qty,
            unit_cost: i.unit_cost,
            lead_time_days: i.lead_time_days
          })),
          budget: budget.value
        }
        const order = await api.createRestockOrder(payload)
        successMessage.value = t('restocking.orderPlaced', { orderNumber: order.order_number })
        // Reset all quantities to 0 so nothing is selected after submit
        forecasts.value.forEach(f => { quantities[f.item_sku] = 0 })
      } catch (err) {
        error.value = 'Failed to place restocking order: ' + err.message
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      loading,
      error,
      forecasts,
      budget,
      quantities,
      successMessage,
      recommendations,
      includedItems,
      totalCost,
      overBudget,
      formatCurrency,
      placeOrder,
      Math
    }
  }
}
</script>

<style scoped>
.budget-card {
  margin-bottom: 1.25rem;
}

.budget-controls {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.slider-row {
  display: flex;
  align-items: center;
  gap: 1.25rem;
}

.budget-slider {
  flex: 1;
  height: 6px;
  accent-color: #2563eb;
  cursor: pointer;
}

.budget-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  min-width: 120px;
  text-align: right;
}

.usage-bar-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.usage-label {
  font-size: 0.875rem;
  color: #64748b;
}

.usage-track {
  width: 100%;
  height: 10px;
  background: #e2e8f0;
  border-radius: 5px;
  overflow: hidden;
}

.usage-fill {
  height: 100%;
  background: #2563eb;
  border-radius: 5px;
  transition: width 0.3s ease, background 0.3s ease;
}

.usage-fill.over-budget {
  background: #dc2626;
}

.over-budget-warning {
  font-size: 0.813rem;
  color: #dc2626;
  font-weight: 600;
}

.total-cost-label {
  font-size: 0.938rem;
  color: #64748b;
}

.total-cost-label strong {
  color: #0f172a;
}

.qty-input {
  width: 72px;
  padding: 0.25rem 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 0.875rem;
  color: #0f172a;
  text-align: right;
}

.qty-input:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 2px #dbeafe;
}

.row-excluded {
  opacity: 0.45;
}

.order-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 1rem;
  margin-top: 0.5rem;
  border-top: 1px solid #e2e8f0;
}

.place-order-btn {
  padding: 0.625rem 1.5rem;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.success-message {
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  color: #065f46;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
  font-size: 0.938rem;
  font-weight: 500;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}
</style>
