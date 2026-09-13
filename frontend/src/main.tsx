import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'sonner'
import { queryClient } from './api'
import App from './App'
import 'katex/dist/katex.min.css'
import './styles.css'
import './workflows.css'

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><App/></BrowserRouter><Toaster position="top-center" richColors closeButton duration={4000}/></QueryClientProvider></React.StrictMode>)
