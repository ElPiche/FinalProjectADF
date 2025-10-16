package com.da.extractor.repository;

import com.da.extractor.model.EtlConfiguration;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * Repositorio para acceder a las configuraciones ETL almacenadas en MongoDB.
 *
 * Funcionalidades:
 * - Búsqueda de configuraciones por modo de ejecución
 * - Filtrado por configuraciones activas
 * - Operaciones CRUD básicas para configuraciones
 */
@Repository
public interface EtlConfigurationRepository extends MongoRepository<EtlConfiguration, String> {

    /**
     * Encuentra todas las configuraciones activas por modo
     * @param mode Modo de ejecución ("batch" o "streaming")
     * @param enabled Si la configuración está activa
     * @return Lista de configuraciones que coinciden
     */
    List<EtlConfiguration> findByModeAndEnabled(String mode, Boolean enabled);

    /**
     * Encuentra todas las configuraciones activas
     * @param enabled Si la configuración está activa
     * @return Lista de configuraciones activas
     */
    List<EtlConfiguration> findByEnabled(Boolean enabled);

    /**
     * Encuentra configuración por nombre de job
     * @param jobName Nombre único del job
     * @return Configuración encontrada o null
     */
    EtlConfiguration findByJobName(String jobName);
    void deleteByJobName(String jobName);
}
