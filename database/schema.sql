-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tenants Table
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Properties Table
CREATE TABLE properties (
    id TEXT NOT NULL, -- Not PK solely, might be composite with tenant in real world, but strict ID here
    tenant_id TEXT REFERENCES tenants(id),
    name TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (id, tenant_id)
);

-- Reservations Table
CREATE TABLE reservations (
    id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL,                          -- Fix: NOT NULL enforces FK integrity
    tenant_id TEXT NOT NULL REFERENCES tenants(id),    -- Fix: NOT NULL prevents orphaned records
    check_in_date TIMESTAMP WITH TIME ZONE NOT NULL,
    check_out_date TIMESTAMP WITH TIME ZONE NOT NULL,
    total_amount NUMERIC(19, 4) NOT NULL,              -- Fix: NUMERIC(19,4) for proper financial precision
    currency TEXT DEFAULT 'USD',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (property_id, tenant_id) REFERENCES properties(id, tenant_id)
);

-- RLS Policies
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE reservations ENABLE ROW LEVEL SECURITY;

-- Fix: Actual RLS policies to enforce tenant isolation.
-- Without these, enabling RLS alone blocks all access — policies define what IS allowed.
CREATE POLICY tenant_isolation_properties ON properties
    USING (tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_isolation_reservations ON reservations
    USING (tenant_id = current_setting('app.current_tenant_id', true));
