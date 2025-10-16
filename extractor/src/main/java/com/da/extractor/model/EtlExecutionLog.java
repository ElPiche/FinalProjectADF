package com.da.extractor.model;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * Modelo que registra los metadatos de ejecución de cada job ETL.
 * Almacena información de auditoría y monitoreo de las ejecuciones.
 *
 * Funcionalidades:
 * - Rastreo de tiempo de ejecución
 * - Estado de la ejecución (éxito/error)
 * - Conteo de registros procesados
 * - Mensajes de error para debugging
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Document(collection = "etl_execution_logs")
public class EtlExecutionLog {

    @Id
    private String id;

    /**
     * ID del job ETL que se ejecutó
     */
    private String jobId;

    /**
     * Nombre del job ETL
     */
    private String jobName;

    /**
     * Modo de ejecución utilizado
     */
    private String mode;

    /**
     * Timestamp de inicio de la ejecución
     */
    private LocalDateTime startTime;

    /**
     * Timestamp de finalización de la ejecución
     */
    private LocalDateTime endTime;

    /**
     * Duración en milisegundos
     */
    private Long durationMs;

    /**
     * Estado de la ejecución: SUCCESS, ERROR, RUNNING
     */
    private String status;

    /**
     * Número de registros extraídos de Elasticsearch
     */
    private Long recordsExtracted;

    /**
     * Número de registros procesados/transformados
     */
    private Long recordsProcessed;

    /**
     * Número de registros insertados en MongoDB
     */
    private Long recordsLoaded;

    /**
     * Mensaje de error si la ejecución falló
     */
    private String errorMessage;

    /**
     * Datos adicionales de la ejecución
     */
    private Map<String, Object> metadata;
}
