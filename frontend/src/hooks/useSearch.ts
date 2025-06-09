/**
 * Search hook for property queries
 * Handles parse → search pipeline with error handling and retries
 */
import { useState, useCallback } from 'react'

export interface PropertyPin {
  id: string
  latitude: number
  longitude: number
  price: number
}

export interface SearchState {
  data: PropertyPin[]
  loading: boolean
  error: string | null
  parsing: boolean
}

interface ParseResponse {
  beds: number
  baths: number
  city: string
  max_price: number
  confidence: number
}

interface SearchResponse {
  results: Array<{
    id: string
    latitude: number
    longitude: number
    price: number
    beds: number
    baths: number
    city: string
  }>
  total: number
  query_time_ms: number
}

const QUERY_SERVICE_URL = '/query'

export const useSearch = () => {
  const [state, setState] = useState<SearchState>({
    data: [],
    loading: false,
    error: null,
    parsing: false
  })

  const search = useCallback(async (query: string): Promise<void> => {
    if (!query?.trim()) {
      setState(prev => ({ ...prev, error: 'Query cannot be empty' }))
      return
    }

    setState({
      data: [],
      loading: true,
      error: null,
      parsing: true
    })

    try {
      // Step 1: Parse the query
      const parseResponse = await parseQuery(query)
      
      setState(prev => ({ ...prev, parsing: false }))
      
      // Step 2: Search with parsed parameters
      const searchResponse = await searchProperties(parseResponse)
      
      // Transform results to pins
      const pins: PropertyPin[] = searchResponse.results.map(result => ({
        id: result.id,
        latitude: result.latitude,
        longitude: result.longitude,
        price: result.price
      }))

      setState({
        data: pins,
        loading: false,
        error: null,
        parsing: false
      })

    } catch (error) {
      setState({
        data: [],
        loading: false,
        error: error instanceof Error ? error.message : 'Search failed',
        parsing: false
      })
    }
  }, [])

  const parseQuery = async (query: string, retryCount = 0): Promise<ParseResponse> => {
    try {
      const response = await fetch(
        `${QUERY_SERVICE_URL}/parse?q=${encodeURIComponent(query)}`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        }
      )

      if (!response.ok) {
        if (response.status >= 500 && retryCount < 1) {
          // Retry once on 5xx errors
          await new Promise(resolve => setTimeout(resolve, 1000))
          return parseQuery(query, retryCount + 1)
        }
        
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          errorData.detail?.detail || 
          errorData.detail?.error || 
          `Parse failed: ${response.status}`
        )
      }

      return await response.json()
    } catch (error) {
      if (error instanceof TypeError) {
        throw new Error('Network error - unable to reach query service')
      }
      throw error
    }
  }

  const searchProperties = async (params: ParseResponse): Promise<SearchResponse> => {
    try {
      const response = await fetch(`${QUERY_SERVICE_URL}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          beds: params.beds,
          baths: params.baths,
          city: params.city.toLowerCase(),
          max_price: params.max_price,
          limit: 50
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          errorData.detail?.detail || 
          errorData.detail?.error || 
          `Search failed: ${response.status}`
        )
      }

      return await response.json()
    } catch (error) {
      if (error instanceof TypeError) {
        throw new Error('Network error - unable to reach search service')
      }
      throw error
    }
  }

  const clearResults = useCallback(() => {
    setState({
      data: [],
      loading: false,
      error: null,
      parsing: false
    })
  }, [])

  return {
    ...state,
    search,
    clearResults
  }
} 