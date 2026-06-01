import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'

export async function POST(req: NextRequest) {
  try {
    const secret = process.env.GITHUB_WEBHOOK_SECRET || ''
    const signature = req.headers.get('x-hub-signature-256') || ''
    const body = await req.text()

    // Verify signature
    const hmac = crypto.createHmac('sha256', secret)
    hmac.update(body)
    const expected = 'sha256=' + hmac.digest('hex')

    if (signature !== expected) {
      return NextResponse.json(
        { error: 'Invalid signature' }, 
        { status: 401 }
      )
    }

    const payload = JSON.parse(body)

    // Only process successful deployments
    if (
      payload.deployment_status?.state !== 'success'
    ) {
      return NextResponse.json({ 
        received: true, 
        skipped: 'not a successful deployment' 
      })
    }

    // Get the deployment URL
    const deployUrl = 
      payload.deployment?.payload?.web_url ||
      payload.repository?.homepage ||
      payload.repository?.html_url

    // Trigger a scan on the deployed URL
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL 
      || 'http://localhost:8000'
    
    // Fire and forget — don't wait for scan to complete
    fetch(`${backendUrl}/scan?url=${encodeURIComponent(deployUrl)}`)
      .catch(err => console.error('Scan failed:', err))

    return NextResponse.json({ 
      received: true,
      scanning: deployUrl 
    })

  } catch (err) {
    console.error('Webhook error:', err)
    return NextResponse.json(
      { error: 'Internal error' }, 
      { status: 500 }
    )
  }
}
