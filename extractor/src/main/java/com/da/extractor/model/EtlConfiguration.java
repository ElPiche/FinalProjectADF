package com.da.extractor.model;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * Modelo que representa la configuración de un job ETL.
 * Cada configuración define cómo extraer datos de Elasticsearch y dónde almacenarlos en MongoDB.
 *
 * Funcionalidades:
 * - Define el modo de ejecución (batch o streaming)
 * - Especifica consultas de Elasticsearch
 * - Configura ventanas de tiempo y frecuencias
 * - Determina la colección de destino
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Document(collection = "etl_configurations")
public class EtlConfiguration {

    @Id
    private String id;

    /**
     * Nombre único del job ETL
     */
    private String jobName;

    /**
     * Modo de ejecución: "batch" o "streaming"
     */
    private String mode;

    /**
     * Query DSL de Elasticsearch en formato JSON
     */
    private Map<String, Object> elasticsearchQuery;

    /**
     * Índice de Elasticsearch donde buscar
     */
    private String elasticsearchIndex;

    /**
     * Ventana de tiempo para extracción (ej: "1h", "1d", "1M")
     */
    private String timeWindow;

    /**
     * Frecuencia de ejecución para modo streaming (en minutos)
     */
    private Integer frequencyMinutes;

    /**
     * Colección MongoDB de destino para los datos procesados
     */
    private String targetCollection;

    /**
     * Si está activa la configuración
     */
    private Boolean enabled = true;

    /**
     * Fecha de creación de la configuración
     */
    private LocalDateTime createdAt;

    /**
     * Fecha de última modificación
     */
    private LocalDateTime updatedAt;

    /**
     * Descripción del propósito del job
     */
    private String description;
}
